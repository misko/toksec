from toksec.stages import SUPPORTED_STAGES, number as stage_number
def profile(language='rust', level=1):
    if level not in SUPPORTED_STAGES:
        raise ValueError('unsupported stage')
    if language == 'cpp':
        return {'language': 'cpp', 'compiler': 'g++', 'edition': 'c++20', 'optimization': 3,
                'source': 'main.cpp', 'approved_libraries': ['C++ standard library', 'C standard library', 'POSIX/Linux OS APIs'] + (['OpenSSL'] if level in (10, 15) else [])}
    if language != 'rust':
        raise ValueError('language must be rust or cpp')
    return {'language': 'rust', 'compiler': 'rustc', 'edition': '2021', 'optimization': 3,
            'source': 'main.rs', 'approved_libraries': ['libc'] + (['OpenSSL FFI'] if level in (10, 15) else [])}


def source_name(manifest):
    return profile(manifest.get('language', 'rust'), stage_number(manifest))['source']
