import unittest
import json
import tempfile
import shutil
from pathlib import Path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from unittest.mock import patch

# Mock the config directory before testing
import storage.roles

class TestCreateRole(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mock_config_dir = Path(self.test_dir)
        self.mock_roles_file = self.mock_config_dir / "roles.json"
        
        # Patch the constants
        self.patcher1 = patch('storage.roles.CONFIG_DIR', self.mock_config_dir)
        self.patcher2 = patch('storage.roles.ROLES_FILE', self.mock_roles_file)
        self.patcher3 = patch('storage.roles.MATERIALS_BASE', self.mock_config_dir / "materials")
        
        self.patcher1.start()
        self.patcher2.start()
        self.patcher3.start()

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()
        shutil.rmtree(self.test_dir)

    def test_create_basic_role(self):
        # Tests creating a standard custom role
        role_id = storage.roles.create_role("Test Role", "Test Prompt")
        self.assertEqual(role_id, "test_role")
        
        roles = storage.roles.load_roles()
        self.assertIn("test_role", roles)
        self.assertEqual(roles["test_role"]["name"], "Test Role")
        self.assertEqual(roles["test_role"]["system_prompt"], "Test Prompt")

    def test_create_role_empty_name(self):
        # Tests fallback for empty name inputs
        role_id = storage.roles.create_role("   ", "Prompt")
        self.assertEqual(role_id, "custom_role")

    def test_create_role_special_characters(self):
        # Tests sanitization to prevent path traversal issues
        role_id = storage.roles.create_role("Super@Role! 123", "Prompt")
        self.assertEqual(role_id, "super_role__123")

    def test_create_role_collision(self):
        # Tests counter increment for duplicate names
        storage.roles.create_role("Dev", "Prompt 1")
        r2 = storage.roles.create_role("Dev", "Prompt 2")
        r3 = storage.roles.create_role("Dev", "Prompt 3")
        
        self.assertEqual(r2, "dev_1")
        self.assertEqual(r3, "dev_2")

    def test_create_role_collision_with_builtin(self):
        # Tests that built-in roles are not overwritten
        r1 = storage.roles.create_role("Negotiator", "My Prompt")
        self.assertEqual(r1, "negotiator_1")

if __name__ == "__main__":
    unittest.main()
