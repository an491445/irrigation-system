from utils.Driver import Driver
from config import MOCK_HARDWARE
import time
import drivers.MCP3008 as MCP3008
from datetime import datetime
import pytz
from config import MOCK_HARDWARE
filename = 'mock' if MOCK_HARDWARE else 'main'

method_defaults = {
  'run': {
    'min_pause': 60,
    'response': {
      'success': {
        'name': 'Success',
        'unit': 'boolean',
      },
      'duration': {
        'name': 'Duration',
        'unit': 'seconds',
      }
    },
    'payload': {
      'duration': {
        'type': 'integer',
        'min': 1,
        'max': 60,
      }
    }
  },
  'switch': {
    'min_pause': 1,
    'response': {
      'success': {
        'name': 'Success',
        'unit': 'boolean',
      },
      'target': {
        'name': 'Current status',
        'unit': 'onoff',
      }
    },
    'payload': {
      'state': {
        'type': 'select',
        'options': [
          { 'value': 'on', 'label': 'On' },
          { 'value': 'off', 'label': 'Off' },
          { 'value': 'toggle', 'label': 'Toggle' },
        ],
      }
    }
  },
  'status': {
    'min_pause': 1,
    'response': {
      'status': {
        'name': 'Status',
        'unit': 'onoff',
      }
    }
  }
}

class MCP23017(Driver):
  def __init__(self, config):
    self.pins = {}
    self.config = config
    self.relays = {}

    Driver.__init__(self, name='MCP23017')

  def _connect_to_hardware(self):
    import board
    import busio
    import adafruit_mcp230xx

    self.i2c = busio.I2C(board.SCL, board.SDA)
    self.sensor = adafruit_mcp230xx.MCP23017(self.i2c)

    self.setup_relays()

  def setup_relays(self):
    for relay in self.config['relays']:
      if "driver" in relay:
        if relay["driver"] == "MCP3008":
          cs = self.setup_pin(relay["pins"]["CS"], True)
          miso = self.get_pin(relay["pins"]["MISO"])
          mosi = self.get_pin(relay["pins"]["MOSI"])
          clk = self.get_pin(relay["pins"]["CLK"])
          mcp3008 = getattr(MCP3008, filename)
          relay['driver'] = mcp3008(relay, cs, miso, mosi, clk)
          self.relays[relay['id']] = relay

      else:
        self.pins[relay['id']] = relay['pin']
        output = relay['output'] if 'output' in relay else False
        self.setup_pin(relay['pin'], output)
        # Transform methods to dictionaries
        methods = {
          item['id']: {
            **method_defaults[item['id']],
            **item,
          }
          for item in relay['methods']
        }
        self.relays[relay['id']] = {
          **relay,
          'methods': methods,
        }

  def get_pin(self, pin):
    return self.sensor.get_pin(pin)

  def setup_pin(self, pin, output=False):
    x = self.get_pin(pin)
    if output:
      x.switch_to_output(value=False)
    return x

  def _input(self, pin):
    try:
      x = self.get_pin(pin)
      return x.value
    except Exception as inst:
      print("Failed to read pin " + str(pin) + " of " + self.name)
      print(type(inst))
      print(inst.args)
      print(inst)
      return None

  def _output(self, pin, status):
    try:
      x = self.get_pin(pin)
      x.value = status
      return True
    except Exception as inst:
      print("Failed to call pin " + str(pin) + " of " + self.name)
      print(type(inst))
      print(inst.args)
      print(inst)
      return False

  def invoke(self, method, payload={}):
    print("Invoking method {} on {} with payload {}".format(method, self.name, payload))
    relay = payload.pop("relay", None)
    # Relay must exist
    self._relay_exists(relay)
    # If relay has no driver, use methods in this file
    if 'driver' not in self.relays[relay]:
      self._validate_payload(method, relay, payload)
      self._enough_time_elapsed(method, relay)

      if relay not in self.method_calls:
        self.method_calls[relay] = {}
      self.method_calls[relay][method] = {'timestamp': datetime.now(pytz.timezone('Europe/Stockholm'))}

      try:
        result = getattr(self, "_{}".format(method))(relay, payload)
        self.method_calls[relay][method]['value'] = result
        return {
          relay: result,
        }
      except AttributeError:
        raise NotImplementedError
    else:
      return {
        relay: self.relays[relay]['driver'].invoke(method, payload)
      }

  def _relay_exists(self, relay):
    if not relay or relay not in self.relays:
      raise ValueError("Relay {} not found".format(relay))

  def _validate_payload(self, method, relay, payload):
    # Method must be 'read', 'switch' or 'run'
    if method not in ['status', 'switch', 'run']:
      raise ValueError("Method {} not found".format(method))
    # Furthermore, method must be allowed for given relay
    if method not in self.relays[relay]['methods']:
      raise ValueError("Method {} not allowed for {}".format(method, relay))
    try:
      getattr(self, "_validate_{}_payload".format(method))(relay, payload)
    except AttributeError:
      return True

  # Make sure enough time has passed since last call
  def _enough_time_elapsed(self, method, relay):
    last_call = self.method_calls.get(relay, {}).get(method)
    # Minimum pause between calls (defaults to 60 seconds)
    min_pause = self.relays[relay]['methods'][method].get('min_pause', 60)

    if last_call is not None and last_call['timestamp'] is not None and \
       (datetime.now(pytz.timezone('Europe/Stockholm')) - last_call['timestamp']).total_seconds() < min_pause:
      raise Exception('not enough time elapsed since last call!')

  def _status(self, relay, payload={}):
    return {
      'status': self._input(self.relays[relay]['pin']),
    }

  def _validate_switch_payload(self, relay, payload):
    if payload['status'] not in ['on', 'off', 'toggle']:
      raise ValueError("Status {} not allowed. Must be on, off or toggle".format(payload['status']))

  def _switch(self, relay, payload={}):
    status = payload['status']
    target = 0
    if status == 'on':
      target = 1
    elif status == 'toggle':
      current = self._input(self.relays[relay]['pin'])
      if current == 0:
        target = 1

    return {
      'success': self._output(self.relays[relay]['pin'], target),
      'target': target == 1,
    }

  def _validate_run_payload(self, relay, payload):
    duration = payload['duration']
    min_duration = self.relays[relay]['methods']['run']['payload']['duration']['min']
    max_duration = self.relays[relay]['methods']['run']['payload']['duration']['max']
    if not isinstance(duration, int):
      raise ValueError("Duration must be integer (given: {})".format(duration))
    if duration > max_duration:
      raise ValueError("Duration must be less than {}".format(max_duration))
    if duration < min_duration:
      raise ValueError("Duration must be at least {}".format(min_duration))

  def _run(self, relay, payload={}):
    try:
      # On
      self._output(self.pins[relay], 1)

      # Wait for `duration` seconds
      time.sleep(payload['duration'])

      # Off
      self._output(self.pins[relay], 0)

      return {
        'success': True,
        'duration': payload['duration'],
      }
    except:
      return {
        'success': False,
        'duration': payload['duration'],
      }

  def _shutdown(self):
    success = True
    for _, relay in self.relays.items():
      if 'driver' in relay:
        stopped = relay['driver'].disconnect()
        success = success and stopped
      else:
        status = self._output(relay['pin'], 0)
        success = success and status
    return success

  def to_json(self):
    def display_relay(relay):
      id = relay['id']
      result = {
        'id': id,
        'name': relay['name'],
      }
      if 'driver' in relay:
        result['driver'] = relay['driver'].to_json()
      else:
        result['methods'] = relay['methods']
        result['last_method_calls'] = self.method_calls[id] if id in self.method_calls else {}
      return result

    return {
      'name': self.name,
      'methods': self.methods,
      'healthy': self.is_healthy(),
      'relays': {id:display_relay(relay) for id, relay in self.relays.items()}
    }
