def get_headers(token: str, device_profile: dict = None):
    # Default device profile
    default_profile = {
        'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
        'X-Unity-Version': "2018.4.11f1",
        'X-GA': "v1 1",
        'ReleaseVersion': "OB49"
    }
    if device_profile:
        profile = {**default_profile, **device_profile}
    else:
        profile = default_profile
    return {
        'User-Agent': profile['User-Agent'],
        'Connection': "Keep-Alive",
        'Accept-Encoding': "gzip",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Unity-Version": profile['X-Unity-Version'],
        "X-GA": profile['X-GA'],
        "ReleaseVersion": profile['ReleaseVersion']
    } 