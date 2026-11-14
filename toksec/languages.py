def profile(language='rust', level=1):
    if level not in range(1, 6):
        raise ValueError('level must be 1 through 5')
    if language == 'cpp':
        return {'language': 'cpp', 'compiler': 'g++', 'edition': 'c++20', 'optimization': 3,
                'source': 'main.cpp', 'approved_libraries': ['C++ standard library', 'C standard library', 'POSIX/Linux OS APIs']}
    if language != 'rust':
        raise ValueError('language must be rust or cpp')
    return {'language': 'rust', 'compiler': 'rustc', 'edition': '2021', 'optimization': 3,
            'source': 'main.rs', 'approved_libraries': ['libc']}


def source_name(manifest):
    return profile(manifest.get('language', 'rust'), manifest['level'])['source']
