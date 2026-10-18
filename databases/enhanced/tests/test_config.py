import unittest
from animal_shelter.config import MongoConfig
from animal_shelter.errors import ConfigurationError

class ConfigurationTests(unittest.TestCase):
    def test_environment_loads_defaults_and_hides_uri_from_repr(self):
        config = MongoConfig.from_env({'MONGODB_URI': 'mongodb://user:SECRET@localhost/'})
        self.assertEqual(config.database, 'aac')
        self.assertEqual(config.timeout_ms, 5000)
        self.assertNotIn('SECRET', repr(config))

    def test_custom_names_and_timeout(self):
        config = MongoConfig.from_env({'MONGODB_URI': 'mongodb://localhost/',
             'MONGODB_DATABASE': 'aac_test', 'MONGODB_COLLECTION': 'animals_test', 'MONGODB_TIMEOUT_MS': '1000'})
        self.assertEqual((config.database, config.collection, config.timeout_ms), ('aac_test', 'animals_test', 1000))

    def test_missing_uri_wrong_scheme_and_invalid_timeout(self):
        for env in ({}, {'MONGODB_URI': 'https://example.com'},
                    {'MONGODB_URI': 'mongodb://localhost/', 'MONGODB_TIMEOUT_MS': 'bad'},
                    {'MONGODB_URI': 'mongodb://localhost/', 'MONGODB_TIMEOUT_MS': '0'}):
            with self.subTest(env=env), self.assertRaises(ConfigurationError):
                MongoConfig.from_env(env)

    def test_direct_configuration_is_validated(self):
        for kwargs in ({'database': 'bad.name'}, {'collection': '$bad'}, {'timeout_ms': True}, {'timeout_ms': 60001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ConfigurationError):
                MongoConfig('mongodb://localhost/', **kwargs)
