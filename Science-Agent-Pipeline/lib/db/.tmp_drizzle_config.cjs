const path = require('path');

module.exports = {
  schema: path.join(__dirname, './src/schema/index.ts'),
  dialect: 'postgresql',
  dbCredentials: {
    url: process.env.DATABASE_URL,
  },
};
