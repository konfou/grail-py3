"""Extension loader for filetype handlers.

The extension objects provided by MIMEExtensionLoader objects have four
attributes: parse, embed, add_options, and update_options.  The first two
are used as handlers for supporting the MIME type as primary and embeded
resources.  The last two are (currently) only used for printing.
"""
__version__ = '$Revision: 2.4 $'


from . import extloader


class MIMEExtensionLoader(extloader.ExtensionLoader):
    def find(self, name):
        new_name = name.replace("-", "_")
        major, minor = new_name.split("/")
        if minor:
            modname = "{}_{}".format(major, minor)
        else:
            modname = major
        mod = self.find_module(modname)
        ext = None
        if not mod and modname != major:
            ext = self.get(major + "/")
        elif mod:
            ext = MIMETypeExtension(name, mod, modname)
        return ext


class MIMETypeExtension:
    def __init__(self, type, mod, modname):
        self.type = type
        self.__load_attr(mod, "parse_" + modname, "parse")
        self.__load_attr(mod, "embed_" + modname, "embed")
        self.__load_attr(mod, "add_options")
        self.__load_attr(mod, "update_settings")

    def __repr__(self):
        classname = type(self).__name__
        modulename = type(self).__module__
        if self.parse and self.embed:
            flags = " [displayable, embeddable]"
        elif self.embed:
            flags = " [embeddable]"
        elif self.parse:
            flags = " [displayable]"
        else:
            # not very useful, now is it?
            flags = ""
        fmt = "<{}.{} for {}{}>"
        return fmt.format(modulename, classname, self.type, flags)

    def __load_attr(self, mod, name, load_as=None):
        load_as = load_as or name
        v = getattr(mod, name, None)
        setattr(self, load_as, v)
