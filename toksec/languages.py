from toksec.stages import number as stage_number
def profile(language='rust', level=1):
    if level not in (1, 2, 3, 4, 5, 10):
        raise ValueError('level must be 1 through 5 or 10')
    if language == 'cpp':
        return {'language': 'cpp', 'compiler': 'g++', 'edition': 'c++20', 'optimization': 3,
                'source': 'main.cpp', 'approved_libraries': ['C++ standard library', 'C standard library', 'POSIX/Linux OS APIs'] + (['OpenSSL'] if level == 10 else [])}
    if language != 'rust':
        raise ValueError('language must be rust or cpp')
    return {'language': 'rust', 'compiler': 'rustc', 'edition': '2021', 'optimization': 3,
            'source': 'main.rs', 'approved_libraries': ['libc'] + (['OpenSSL FFI'] if level == 10 else [])}


def source_name(manifest):
    return profile(manifest.get('language', 'rust'), stage_number(manifest))['source']
