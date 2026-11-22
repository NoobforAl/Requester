from django.conf import settings


def languages(request):
    """The language switcher's choices, each named in its own language.

    ``{% get_available_languages %}`` would run the names through gettext (so the
    English entry would read "angličtina" to a Czech visitor); native names must not
    be translated.
    """
    return {"LANGUAGE_CHOICES": settings.LANGUAGES}
