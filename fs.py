import errno
import stat
import os
from time import time
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
from pointcarre import PointCarre

Now = time()
Uid, Gid = os.getuid(), os.getgid()


def wrap_enoent(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyError:
            raise FuseOSError(errno.ENOENT)
    return wrapper


class Node(object):
    def __init__(self, name, is_leaf=False):
        self.name = name
        self.is_leaf = is_leaf

    def get_by_path(self, path=[]):
        while len(path) > 0 and path[0] == '':
            path = path[1:]
        if len(path) == 0:
            return self
        for child in self.children:
            if child.name == path[0]:
                return child.get_by_path(path[1:])
        raise KeyError()

    def tree(self, indent=''):
        print indent + self.name
        if not self.is_leaf:
            for child in self.children:
                child.tree(indent + "  ")

    def stat(self):
        mode = (0644 | stat.S_IFREG) if self.is_leaf else (0755 | stat.S_IFDIR)
        return {
            'st_mode': mode,
            'st_ctime': Now,
            'st_mtime': Now,
            'st_atime': Now,
            'st_nlink': 2,
            'st_uid': Uid,
            'st_gid': Gid,
            'st_size': 4096,
        }


class Root(Node):
    def __init__(self):
        super(Root, self).__init__('ROOT', False)
        self.children = []


class Course(Node):
    def __init__(self, name, pointcarre_client, course_id):
        super(Course, self).__init__(name, is_leaf=False)
        self.course_id = course_id
        self.client = pointcarre_client

    def build_cat(self, pc_dict):
        cat = Category(pc_dict['text'], self.client, self.course_id, pc_dict['id'])
        for child in pc_dict.get('children', []):
            cat.known_children.append(self.build_cat(child))
        return cat

    @property
    def children(self):
        categories = self.client.get_tree_layout(self.course_id)
        return [self.build_cat(categories)]


class Category(Course):
    def __init__(self, name, client, course_id, cat_id):
        super(Category, self).__init__(name, client, course_id)
        self.cat_id = cat_id
        self.known_children = []

    @property
    def children(self):
        res = self.known_children
        documents = self.client.get_tree_node(self.course_id, self.cat_id)
        return res + [
            Document(name, self.client, self.course_id, self.cat_id, doc_id)
            for name, doc_id in documents.iteritems()]


class Document(Node):
    def __init__(self, name, client, course_id, cat_id, doc_id):
        super(Document, self).__init__(name, is_leaf=True)
        self.client = client
        self.ids = (course_id, cat_id, doc_id)

    def stat(self):
        res = super(Document, self).stat()
        res['st_size'] = self.client.get_document_size(*self.ids)
        return res

    @property
    def content(self):
        return self.client.get_document(*self.ids)


class FileSystem(LoggingMixIn, Operations):
    def __init__(self, client):
        self.root = Root()
        self.client = client
        for name, course_id in client.get_courses().iteritems():
            course = Course(name=name, pointcarre_client=client, course_id=course_id)
            self.root.children.append(course)

    # FUSE INTERFACE #
    @wrap_enoent
    def getattr(self, path, fh=None):
        return self.root.get_by_path(path.split('/')).stat()

    @wrap_enoent
    def readdir(self, path, fh=None):
        node = self.root.get_by_path(path.split('/'))
        return ['.', '..'] + [child.name for child in node.children]

    @wrap_enoent
    def read(self, path, size, offset, fh=None):
        node = self.root.get_by_path(path.split('/'))
        return node.content[offset:size+offset]

if __name__ == "__main__":
    from sys import argv

    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)

    fs = FileSystem(PointCarre.cached_session())
    fuse = FUSE(fs, argv[1], foreground=True)
