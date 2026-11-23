"""Shared form helpers."""

from django.forms.renderers import BaseRenderer, Jinja2

# Django's built-in widget templates, rendered with Jinja2: the same markup, about
# twice as fast. It matters for the skills checkboxes and selects, where Django
# renders one sub-template per option (5-7 ms per widget with ~50 skills, on every
# job list page). Not the global FORM_RENDERER: the admin's widgets only exist as
# Django templates.
FAST_RENDERER = Jinja2()


class FastRenderMixin:
    """Render this form's widgets with :data:`FAST_RENDERER`."""

    default_renderer: BaseRenderer | type[BaseRenderer] | None = FAST_RENDERER
