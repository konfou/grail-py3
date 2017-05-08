from . import nullAPI


class data_access(nullAPI.null_access):
    def __init__(self, url, method, params):
        if method != "GET":
            msg = "'data:' scheme does not support the {} method"
            raise IOError(msg.format(method))
        self.state = nullAPI.META
        self.__ctype, self.__data = parse(url)

    def getmeta(self):
        assert self.state == nullAPI.META
        self.state = nullAPI.DATA
        headers = {"content-type": self.__ctype,
                   "content-length": format(len(self.__data)),
                   }
        if self.__data:
            return 200, "Ready", headers
        return 204, "No content", headers

    def polldata(self):
        assert self.state in (nullAPI.META, nullAPI.DATA)
        return "Ready", True

    def getdata(self, maxbytes):
        assert self.state == nullAPI.DATA
        data = self.__data[:maxbytes]
        self.__data = self.__data[maxbytes:]
        if not data:
            self.state = nullAPI.DONE
        return data


def parse(url):
    ctype, data, encoding = None, "", "raw"
    pos = url.find(';')
    if pos >= 0:
        ctype = url[:pos].strip().lower()
        url = url[pos + 1:]
    pos = url.find(',')
    if pos >= 0:
        encoding = url[:pos].strip().lower()
        url = url[pos + 1:]
    data = url.encode()
    if data and encoding == "base64":
        import base64
        data = base64.decodebytes(data)
    return (ctype or "text/plain"), data
