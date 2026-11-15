from stages.common.performance import matrix


def workloads():
    return matrix([('fresh', False, False, False, '/data/'), ('persistent', True, False, False, '/data/')])
