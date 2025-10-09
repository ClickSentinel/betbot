"""
Test suite for Discord.py extension loading and cog setup functions.
Ensures all cogs have proper setup() functions and can be loaded as extensions.
"""

import pytest
import importlib
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)


class TestCogSetupFunctions:
    """Test that all cogs have proper setup functions for Discord.py extensions."""

    COG_MODULES = [
        "cogs.bet_commands",
        "cogs.reaction_handler",
        "cogs.live_message_manager",
        "cogs.session_manager",
        "cogs.bet_utils",
        "cogs.economy",
        "cogs.help",
        "cogs.betting",  # Legacy cog, may not have setup function
    ]

    def test_all_cog_modules_exist(self):
        """Test that all expected cog modules can be imported."""
        for module_name in self.COG_MODULES:
            try:
                module = importlib.import_module(module_name)
                assert module is not None, f"Failed to import {module_name}"
            except ImportError as e:
                # betting.py might not exist or be a legacy module
                if "betting" not in module_name:
                    pytest.fail(f"Failed to import {module_name}: {e}")

    def test_cog_classes_exist(self):
        """Test that each cog module has a Cog class."""
        for module_name in self.COG_MODULES:
            try:
                module = importlib.import_module(module_name)

                # Find classes that inherit from discord.ext.commands.Cog
                cog_classes = []
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                        hasattr(obj, '__bases__') and
                        any('Cog' in str(base) for base in obj.__bases__)):
                        cog_classes.append((name, obj))

                assert len(cog_classes) > 0, f"No Cog classes found in {module_name}"
                # Allow multiple cogs per module (some modules may have utility cogs)
                assert len(cog_classes) >= 1, f"No Cog classes found in {module_name}"

                cog_name, cog_class = cog_classes[0]
                # Check that cog names are reasonable (not too strict)
                assert len(cog_name) > 3, f"Cog class name should be descriptive: {cog_name}"

            except ImportError:
                # Skip betting module if it doesn't exist
                if "betting" not in module_name:
                    pytest.fail(f"Failed to check cog class in {module_name}")

    def test_setup_functions_exist(self):
        """Test that all cog modules have async setup(bot) functions."""
        for module_name in self.COG_MODULES:
            try:
                module = importlib.import_module(module_name)

                # Check for setup function
                assert hasattr(module, 'setup'), f"No setup function found in {module_name}"

                setup_func = getattr(module, 'setup')
                assert callable(setup_func), f"setup is not callable in {module_name}"

                # Check if it's a coroutine function (async)
                assert inspect.iscoroutinefunction(setup_func), f"setup is not async in {module_name}"

                # Check signature
                sig = inspect.signature(setup_func)
                params = list(sig.parameters.keys())
                assert len(params) == 1, f"setup should have exactly 1 parameter in {module_name}, got {params}"
                assert params[0] == 'bot', f"setup parameter should be 'bot' in {module_name}, got {params[0]}"

            except ImportError:
                # betting.py might not have setup function (legacy)
                if "betting" not in module_name:
                    pytest.fail(f"Failed to check setup function in {module_name}")

    @pytest.mark.asyncio
    async def test_setup_functions_callable(self):
        """Test that setup functions can be called with a mock bot."""
        for module_name in self.COG_MODULES:
            try:
                module = importlib.import_module(module_name)

                if not hasattr(module, 'setup'):
                    # Skip betting module
                    if "betting" in module_name:
                        continue
                    pytest.fail(f"No setup function in {module_name}")

                setup_func = getattr(module, 'setup')

                # Create mock bot
                mock_bot = MagicMock()
                mock_bot.add_cog = AsyncMock()

                # Call setup function
                await setup_func(mock_bot)

                # Verify add_cog was called
                mock_bot.add_cog.assert_called_once()

                # Verify the cog instance passed is correct type
                call_args = mock_bot.add_cog.call_args[0]
                cog_instance = call_args[0]

                # Find the expected cog class
                cog_classes = []
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                        hasattr(obj, '__bases__') and
                        any('Cog' in str(base) for base in obj.__bases__)):
                        cog_classes.append(obj)

                if cog_classes:
                    expected_class = cog_classes[0]
                    assert isinstance(cog_instance, expected_class), \
                        f"setup added wrong cog type in {module_name}: expected {expected_class}, got {type(cog_instance)}"

            except ImportError:
                if "betting" not in module_name:
                    pytest.fail(f"Failed to test setup function in {module_name}")

    def test_no_duplicate_setup_functions(self):
        """Test that there are no duplicate setup function definitions."""
        seen_modules = set()
        for module_name in self.COG_MODULES:
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, 'setup'):
                    # Check if we've seen this setup function before
                    setup_id = id(getattr(module, 'setup'))
                    assert setup_id not in seen_modules, f"Duplicate setup function detected in {module_name}"
                    seen_modules.add(setup_id)
            except ImportError:
                pass  # Skip missing modules

    def test_setup_function_documentation(self):
        """Test that setup functions have docstrings."""
        for module_name in self.COG_MODULES:
            try:
                module = importlib.import_module(module_name)

                if hasattr(module, 'setup'):
                    setup_func = getattr(module, 'setup')
                    assert setup_func.__doc__ is not None, f"setup function in {module_name} should have a docstring"
                    assert len(setup_func.__doc__.strip()) > 0, f"setup docstring in {module_name} should not be empty"

            except ImportError:
                if "betting" not in module_name:
                    pytest.fail(f"Failed to check setup documentation in {module_name}")