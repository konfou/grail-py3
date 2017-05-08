"""Parser for XML bookmarks using the XBEL DTD."""

__version__ = '$Revision: 1.10 $'


from .. import iso8601
from .. import nodes
from xml.etree.ElementTree import TreeBuilder
from collections import defaultdict


class Capture(TreeBuilder):
    def __init__(self, tag, attrs):
        TreeBuilder.__init__(self)
        self.__root = self.start(tag, attrs)

    def end(self, tag):
        """Returns True unless this tag marks the end of the captured
        section"""
        element = TreeBuilder.end(self, tag)
        return element is not self.__root


def normalize_capture(data):
    queue = [(data, False)]
    while queue:
        element, preserve = queue.pop(0)
        #
        preserve = preserve or element.get("xml:space") == "preserve"
        #
        if not preserve:
            # remove leading blank:
            if element.text and not element.text.strip():
                element.text = None
            # remove trailing blank
            if len(element):
                text = element[-1].tail
                if text is not None and not text.strip():
                    element[-1].tail = None
            # now, if all remaining strings are blank,
            # assume this is element-only:
            preserve = (element.text is not None and element.text.strip() and
                any(child.tail is not None and child.tail.strip()
                for child in element))
        if not preserve:
            # All internal strings are blank; remove them.
            for child in element:
                child.tail = None
        for citem in content:
            if not isinstance(citem, str):
                queue.append((citem, preserve))


class DocumentHandler:
    """Implements Element Tree's parser TreeBuilder() target interface"""
    
    __folder = None
    __store_node = None

    def __init__(self, filename):
        self.__filename = filename
        self.__context = []
        self.__idmap = {}
        self.__missing_ids = defaultdict(list)
        self.__root = self.new_folder()

    def close(self):
        return self.__root

    def start_xbel(self, attrs):
        self.__store_date(self.__root, attrs, "added", "set_add_date")
        self.handle_id(self.__root, attrs)
    def end_xbel(self):
        pass

    def start_folder(self, attrs):
        self.new_folder(attrs)
    def end_folder(self):
        self.__store_node = None
        self.__folder = self.__context.pop()

    def start_title(self, attrs):
        self.save_bgn()
    def end_title(self):
        self.__store_node.set_title(self.save_end())

    __node = None
    def start_bookmark(self, attrs):
        self.new_bookmark(attrs)
        node = self.__node
        self.handle_id(node, attrs)
        node.set_uri(attrs.get("href", "").strip())
        self.__store_date(node, attrs, "added",    "set_add_date")
        self.__store_date(node, attrs, "visited",  "set_last_visited")
        self.__store_date(node, attrs, "modified", "set_last_modified")
    def end_bookmark(self):
        self.__node = None
        self.__store_node = None

    def start_desc(self, attrs):
        self.save_bgn()
    def end_desc(self):
        desc = self.save_end().strip()
        if desc:
            if self.__node:
                self.__node.set_description(desc)
            else:
                self.__folder.set_description(desc)

    def start_alias(self, attrs):
        alias = nodes.Alias()
        self.handle_idref(alias, attrs)
        self.__folder.append_child(alias)
    def end_alias(self):
        pass

    def start_separator(self, attrs):
        self.__folder.append_child(nodes.Separator())
    def end_separator(self):
        pass

    # metadata methods:

    def start_info(self, attrs):
        pass
    def end_info(self):
        pass

    def start_metadata(self, attrs):
        self.capture_bgn("metadata", attrs)
    def end_metadata(self):
        metadata = self.capture_end()
        normalize_capture(metadata)
        if not metadata[-1]:
            return
        info = self.__node.info()
        if info is None:
            info = []
            self.__node.set_info(info)
        info.append(metadata)

    # support methods:

    def new_bookmark(self, attrs):
        self.__node = nodes.Bookmark()
        self.__store_node = self.__node
        self.__folder.append_child(self.__node)
        return self.__node

    def new_folder(self, attrs={}):
        if self.__folder is not None:
            self.__context.append(self.__folder)
        folded = attrs.get("folded", "no").lower() == "yes"
        self.__folder = nodes.Folder()
        self.__store_node = self.__folder
        if self.__context:
            self.__context[-1].append_child(self.__folder)
        if folded:
            self.__folder.collapse()
        else:
            self.__folder.expand()
        added = attrs.get("added")
        if added:
            try:
                added = iso8601.parse(added)
            except ValueError:
                pass
            else:
                self.__folder.set_add_date(added)
        self.handle_id(self.__folder, attrs)
        return self.__folder

    def handle_id(self, node, attrs, attrname="id", required=False):
        id = attrs.get(attrname)
        if id:
            node.set_id(id)
            self.__idmap[id] = node
            for n in self.__missing_ids.pop(id, ()):
                n.set_idref(node)
        elif required:
            msg = "missing {} attribute".format(attrname)
            raise BookmarkFormatError(self.__filename, msg)

    def handle_idref(self, node, attrs, attrname="ref", required=True):
        idref = attrs.get(attrname)
        if idref:
            if idref in self.__idmap:
                node.set_refnode(self.__idmap[idref])
            else:
                self.__missing_ids[idref].append(node)
        elif required:
            msg = "missing {} attribute".format(attrname)
            raise BookmarkFormatError(self.__filename, msg)

    def __store_date(self, node, attrs, attrname, nodefuncname):
        date = attrs.get(attrname)
        if date:
            func = getattr(node, nodefuncname)
            try:
                date = iso8601.parse(date)
            except ValueError:
                return
            func(date)

    __buffer = ""
    def save_bgn(self):
        self.__buffer = ""

    def save_end(self):
        s, self.__buffer = self.__buffer, ""
        return " ".join(s.split())
    
    __capture = None
    def capture_bgn(self, tag, attrs):
        self.__capture = Capture(tag, attrs)
    
    def capture_end(self):
        capture = self.__capture.close()
        self.__capture = None
        return capture

    def data(self, data):
        if self.__capture:
            self.__capture.data(data)
        else:
            self.__buffer = self.__buffer + data

    def start(self, tag, attrs):
        if self.__capture:
            self.__capture.start(tag, attrs)
            return
        methodname = "start_" + tag
        if hasattr(self, methodname):
            getattr(self, methodname)(attrs)

    def end(self, tag):
        if self.__capture and self.__capture.end(tag):
            return
        methodname = "end_" + tag
        if hasattr(self, methodname):
            getattr(self, methodname)()


from xml.etree.ElementTree import XMLParser


class Parser(XMLParser):
    mode = "b"
    
    def __init__(self, filename):
        XMLParser.__init__(self, target=DocumentHandler(filename))
    
    def close(self):
        self.__root = XMLParser.close(self)
    
    def get_root(self):
        return self.__root
