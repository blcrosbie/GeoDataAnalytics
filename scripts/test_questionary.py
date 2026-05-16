#!/usr/bin/env python3

import questionary

def test_questionary():
    """Test if questionary works without use_indicator parameter."""
    print("Testing questionary without use_indicator...")
    
    # Test checkbox
    try:
        result = questionary.checkbox(
            "Select options:",
            choices=["Option 1", "Option 2", "Option 3"]
        ).ask()
        print(f"Checkbox test passed. Result: {result}")
        return True
    except Exception as e:
        print(f"Checkbox test failed: {e}")
        return False

if __name__ == "__main__":
    test_questionary()