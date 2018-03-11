const config = {}

config.host = process.env.DB_ENDPOINT || "[URI for DocumentDB endpoint]";
config.authKey = process.env.DB_PRIMARY_KEY || "[Master key for DocumentDB]";
config.databaseId = "iotDB";
config.collectionId = "iotMessages";

config.iothubconnection = process.env.IOTHUB_CONNECTION
config.deviceId = 'Huvudsta';

module.exports = config;
