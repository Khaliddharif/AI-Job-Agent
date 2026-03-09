import os
import streamlit.components.v1 as components

# Create a _RELEASE constant. We'll set this to False while we're developing
# the component, and True when we're ready to package and distribute it.
_RELEASE = True

if not _RELEASE:
    _component_func = components.declare_component(
        "turnstile",
        url="http://localhost:3001",
    )
else:
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(parent_dir, "frontend")
    _component_func = components.declare_component("turnstile", path=build_dir)

def turnstile(sitekey: str, key=None):
    """Create a new instance of "turnstile"."""
    component_value = _component_func(sitekey=sitekey, key=key, default=None)
    return component_value
