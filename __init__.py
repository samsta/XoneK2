from importlib import reload
import XoneK2_DJ.xone
import XoneK2_DJ.Browser

def create_instance(c_instance):
    reload(xone)
    reload(Browser)
    return xone.XoneK2_DJ(c_instance)
