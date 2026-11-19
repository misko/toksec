from stages.common.grading.performance import matrix


def workloads():
    return matrix([('fresh', False, False, False, '/data/'), ('persistent', True, False, False, '/data/')])
