def badly_formatted(x: int, y: int, z: int) -> int:
    """Add three numbers together."""
    result = x + y + z
    # Removed unused message variable
    return result


def another_function(a: int, b: int) -> int:
    """Add two numbers together."""
    # Removed unused data variable
    return a + b


class MyClass:
    """Example class with proper type hints."""

    def __init__(self, value: int) -> None:
        """Initialize with a value."""
        self.value = value

    def get_value(self) -> int:
        """Get the stored value."""
        return self.value


def no_type_hints(name: str, age: int, active: bool) -> str | None:
    """Format a person's information."""
    if active:  # Fixed: removed == True
        return f"{name} is {age} years old"
    else:
        return None
