from django.conf import settings


def get_frontend_url(path=''):
    """
    Generate frontend URL by combining FRONTEND_URL with the given path.
    Removes leading slash from path if present to avoid double slashes.
    """
    base_url = settings.FRONTEND_URL.rstrip('/')
    if path:
        path = path.lstrip('/')
        return f"{base_url}/{path}"
    return base_url


def get_lead_frontend_urls(lead_id):
    """Generate frontend URLs for lead-related actions"""
    return {
        'view_lead': get_frontend_url(f'leads/{lead_id}'),
        'edit_lead': get_frontend_url(f'leads/{lead_id}/edit'),
        'assign_lead': get_frontend_url(f'leads/{lead_id}/assign'),
        'convert_lead': get_frontend_url(f'leads/{lead_id}/convert'),
    }


def get_school_frontend_urls(school_id):
    """Generate frontend URLs for school-related actions"""
    return {
        'view_school': get_frontend_url(f'schools/{school_id}'),
        'manage_students': get_frontend_url(f'schools/{school_id}/students'),
        'school_dashboard': get_frontend_url(f'schools/{school_id}/dashboard'),
        'school_settings': get_frontend_url(f'schools/{school_id}/settings'),
    }


def get_demo_frontend_urls(demo_id):
    """Generate frontend URLs for demo-related actions"""
    return {
        'view_demo': get_frontend_url(f'demos/{demo_id}'),
        'edit_demo': get_frontend_url(f'demos/{demo_id}/edit'),
        'join_demo': get_frontend_url(f'demos/{demo_id}/join'),
    }


def get_onboarding_frontend_urls(onboarding_id):
    """Generate frontend URLs for onboarding-related actions"""
    return {
        'view_onboarding': get_frontend_url(f'onboarding/{onboarding_id}'),
        'onboarding_progress': get_frontend_url(f'onboarding/{onboarding_id}/progress'),
        'onboarding_tasks': get_frontend_url(f'onboarding/{onboarding_id}/tasks'),
    }