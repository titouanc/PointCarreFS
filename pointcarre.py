import re
import json
import pickle
import requests
from bs4 import BeautifulSoup
from config import NETID, PASSWORD


def match_get_params(**match):
    def func(a_link):
        url = a_link.attrs.get('href', '')
        for pair in match.items():
            if '%s=%s' % tuple(map(str, pair)) not in url:
                return False
        return True
    return func


def memoize(func):
    known = {}

    def wrapper(*args):
        if args not in known:
            known[args] = func(*args)
        return known[args]
    wrapper.__name__ = "_memoized_" + func.__name__
    return wrapper


doctree_regexp = re.compile(r"var treedata = ([^;]+);")
publication_id_regexp = re.compile(r'publication=(\d+)')
course_id_regexp = re.compile(r'course=(\d+)')


class PointCarre(requests.Session):
    def __init__(self, netid=NETID, password=PASSWORD):
        super(PointCarre, self).__init__()

        # Acquire initial cookies
        login_url = "https://cas.vub.ac.be/cas/login?service=https%3A%2F%2Fpointcarre.vub.ac.be%2Findex.php"
        r = self.get(login_url)

        # Acquire form parameters
        page = BeautifulSoup(r.content, "html.parser")
        lt = page.select("input[name=lt]")[0].attrs["value"]

        login_form = {
            "username": netid,
            "password": password,
            "lt": lt,
            "execution": "e1s1",
            "_eventId": "submit",
            "submit": "LOGIN",
        }
        r = self.post(login_url, data=login_form)

    def get(self, url, *args, **kwargs):
        print "\033[32;1mGET\033[0m", url
        return super(PointCarre, self).get(url, *args, **kwargs)

    def post(self, url, *args, **kwargs):
        print "\033[33;1mPOST\033[0m", url
        return super(PointCarre, self).post(url, *args, **kwargs)

    def head(self, url, *args, **kwargs):
        print "\033[34;1mHEAD\033[0m", url
        return super(PointCarre, self).head(url, *args, **kwargs)

    def query(self, method=None, **params):
        if method is None:
            method = self.get
        params = [
            ('application', 'application%5Cweblcms'), ('go', 'course_viewer'),
            ('tool', 'document'), ('pub_type', '2')] + [
            tuple(map(str, p)) for p in params.iteritems()]

        get_params = '&'.join('%s=%s' % p for p in params)
        url = "https://pointcarre.vub.ac.be/index.php?" + get_params
        return method(url)

    @memoize
    def get_courses(self):
        def courseid(a):
            return int(course_id_regexp.search(a.attrs['href']).group(1))

        page = BeautifulSoup(
            self.get(
                "https://pointcarre.vub.ac.be/index.php?"
                "application=application\weblcms").content,
            "html.parser")

        links = filter(match_get_params(go='course_viewer'), page.select('a'))
        courses_links = filter(lambda l: len(l.text), links)
        return {l.text.strip(): courseid(l) for l in courses_links}

    @memoize
    def get_tree_layout(self, course_id):
        page = BeautifulSoup(
            self.query(course=course_id).content,
            "html.parser")

        js = ''.join(script.text for script in page.select('script'))
        match = doctree_regexp.search(js)
        if match:
            return json.loads(match.group(1))
        raise Exception("Cannot find course tree")

    @memoize
    def get_tree_node(self, course_id, node_id):
        def pubid(a):
            return int(publication_id_regexp.search(a.attrs['href']).group(1))

        page = BeautifulSoup(
            self.query(
                course=course_id, publication_category=node_id,
                browser="table", tool_action="browser").content,
            "html.parser")

        docs_link = filter(
            match_get_params(tool_action="viewer"),
            page.select('a'))

        return {a.text: pubid(a) for a in docs_link if a.text}

    @memoize
    def get_document(self, course_id, node_id, publication_id):
        return self.query(
            course=course_id, publication_category=node_id,
            browser="table", tool_action="downloader",
            publication=publication_id).content

    @memoize
    def get_document_size(self, course_id, node_id, publication_id):
        r = self.query(method=self.head,
            course=course_id, publication_category=node_id,
            browser="table", tool_action="downloader",
            publication=publication_id)
        return int(r.headers['Content-Length'])

    @memoize
    def get_node_zip(self, course_id, node_id):
        return self.query(
            course=course_id, publication_category=node_id,
            browser="table", tool_action="zip_and_download").content

    @classmethod
    def cached_session(cls):
        try:
            res = pickle.load(open(".session"))
        except:
            res = cls()
            pickle.dump(res, open(".session", 'w'))
        return res


if __name__ == "__main__":
    s = PointCarre.cached_session()
    print s.get_courses()
