def profile(language='rust', level=1):
    if language == 'cpp':
        if level not in (1, 2):
            raise ValueError('C++ is currently supported for Stages 1 and 2 only')
        return {'language': 'cpp', 'compiler': 'g++', 'edition': 'c++20', 'optimization': 3,
                'source': 'main.cpp', 'approved_libraries': ['C++ standard library', 'C standard library', 'POSIX/Linux OS APIs']}
    if language != 'rust':
        raise ValueError('language must be rust or cpp')
    return {'language': 'rust', 'compiler': 'rustc', 'edition': '2021', 'optimization': 3,
            'source': 'main.rs', 'approved_libraries': ['libc'] + (['libssl.so.3', 'libcrypto.so.3', 'libz.so.1'] if level == 5 else [])}


def source_name(manifest):
    return profile(manifest.get('language', 'rust'), manifest['level'])['source']
