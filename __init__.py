from importlib import reload
import XoneK2_DJ.xone


def create_instance(c_instance):
    reload(xone)
    return xone.XoneK2_DJ(c_instance)
