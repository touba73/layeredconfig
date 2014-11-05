#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
test_layeredconfig
----------------------------------

Tests for `layeredconfig` module.
"""


import os
import logging
import sys
import codecs
from six import text_type as str
from datetime import date, datetime
import argparse
try:
    from collections import OrderedDict
except ImportError:  # pragma: no cover
    # if on python 2.6
    from ordereddict import OrderedDict

if sys.version_info < (2, 7, 0):  # pragma: no cover
    import unittest2 as unittest
else: 
    import unittest

# The system under test
from layeredconfig import (LayeredConfig, Defaults, INIFile, JSONFile,
                           YAMLFile, PListFile, Environment, Commandline)

class TestConfigSourceHelper(object):
    # Testcases for less-capable sources may override this
    supported_types = (str, int, bool, list, date, datetime)
    supports_nesting = True

    # First, a number of straightforward tests for any
    # ConfigSource-derived object. Concrete test classes should set up
    # self.simple and self.complex instances to match these.
    def test_keys(self):
        self.assertEqual(set(self.simple.keys()),
                         set(('home', 'processes', 'force',
                              'extra', 'expires', 'lastrun')))
        self.assertEqual(set(self.complex.keys()),
                         set(('home', 'processes', 'force', 'extra')))

    def test_subsection_keys(self):
        self.assertEqual(set(self.complex.subsection('mymodule').keys()),
                         set(('force', 'extra', 'expires')))

    def test_subsections(self):
        self.assertEqual(set(self.simple.subsections()),
                         set())
        self.assertEqual(set(self.complex.subsections()),
                         set(('mymodule', 'extramodule')))

    def test_subsection_nested(self):
        subsec = self.complex.subsection('mymodule')
        self.assertEqual(set(subsec.subsections()),
                         set(('arbitrary',)))

    def test_has(self):
        for key in self.simple.keys():
            self.assertTrue(self.simple.has(key))

    def test_typed(self):
        for key in self.simple.keys():
            self.assertTrue(self.simple.typed(key))
                
    def test_get(self):
        # FIXME: This test should be able to look at supported_types
        # like test_singlesection and test_subsections do, so derived
        # testcase classes don't need to override it.
        self.assertEqual(self.simple.get("home"), "mydata")
        self.assertEqual(self.simple.get("processes"), 4)
        self.assertEqual(self.simple.get("force"), True)
        self.assertEqual(self.simple.get("extra"), ['foo', 'bar'])
        self.assertEqual(self.simple.get("expires"), date(2014, 10, 15))
        self.assertEqual(self.simple.get("lastrun"),
                         datetime(2014, 10, 15, 14, 32, 7))

    # Then, two validation helpers for checking a complete
    # LayeredConfig object, where validation can be performed
    # different depending on the abilities of the source (eg. typing)
    def test_config_singlesection(self):
        # each subclass is responsible for creating a self.simple
        # object of the type being tested
        cfg = LayeredConfig(self.simple)

        self.assertIs(type(cfg.home), str)
        self.assertEqual(cfg.home, 'mydata')

        int_type = int if int in self.supported_types else str
        self.assertIs(type(cfg.processes), int_type)
        self.assertEqual(cfg.processes, int_type(4))

        bool_type = bool if bool in self.supported_types else str
        self.assertIs(type(cfg.force), bool_type)
        self.assertEqual(cfg.force, bool_type(True))

        if list in self.supported_types:
            list_type = list
            list_want = ['foo', 'bar']
        else:
            list_type = str
            list_want = "foo, bar"  # recommended list serialization
        self.assertIs(type(cfg.extra), list_type)
        self.assertEqual(cfg.extra, list_want)

        if date in self.supported_types:
            date_type = date
            date_want = date(2014, 10, 15)
        else:
            date_type = str
            date_want = "2014-10-15" # recommended date serialization
        self.assertIs(type(cfg.expires), date_type)
        self.assertEqual(cfg.expires, date_want)

        if datetime in self.supported_types:
            datetime_type = datetime
            datetime_want = datetime(2014, 10, 15, 14, 32, 7)
        else:
            datetime_type = str
            datetime_want = "2014-10-15 14:32:07"
        self.assertIs(type(cfg.lastrun), datetime_type)
        self.assertEqual(cfg.lastrun, datetime_want)

    def test_config_subsections(self):
        cfg = LayeredConfig(self.complex)

        self.assertEqual(cfg.home, 'mydata')
        with self.assertRaises(AttributeError):
            cfg.mymodule.home

        int_type = int if int in self.supported_types else str
        self.assertEqual(cfg.processes, int_type(4))
        with self.assertRaises(AttributeError):
            cfg.mymodule.processes

        bool_type = bool if bool in self.supported_types else str
        self.assertEqual(cfg.force, bool_type(True))
        self.assertEqual(cfg.mymodule.force, bool_type(False))

        if list in self.supported_types:
            list_type = list
            list_want = ['foo', 'bar']
            list_want_sub = ['foo', 'baz']
        else:
            list_type = str
            list_want = "foo, bar"
            list_want_sub = "foo, baz"
        self.assertEqual(cfg.extra, list_want)
        self.assertEqual(cfg.mymodule.extra, list_want_sub)

        # not supported for INIFile
        if self.supports_nesting:
            self.assertEqual(cfg.mymodule.arbitrary.nesting.depth, 'works')

        with self.assertRaises(AttributeError):
            cfg.expires

        if date in self.supported_types:
            date_type = date
            date_want = date(2014, 10, 15)
        else:
            date_type = str
            date_want = "2014-10-15" # recommended date serialization
        self.assertEqual(cfg.mymodule.expires, date_want)


# common helper
class TestINIFileHelper(object):

    def setUp(self):
        super(TestINIFileHelper, self).setUp()
        with open("simple.ini", "w") as fp:
            fp.write("""
[__root__]
home = mydata
processes = 4
force = True
extra = foo, bar
expires = 2014-10-15
lastrun = 2014-10-15 14:32:07
""")

        with open("complex.ini", "w") as fp:
            fp.write("""
[__root__]
home = mydata
processes = 4
force = True
extra = foo, bar

[mymodule]
force = False
extra = foo, baz
expires = 2014-10-15

[extramodule]
unique = True
""")

    def tearDown(self):
        super(TestINIFileHelper, self).tearDown()
        os.unlink("simple.ini")
        os.unlink("complex.ini")


class TestDefaults(unittest.TestCase, TestConfigSourceHelper):

    simple = Defaults({'home': 'mydata',
                       'processes': 4,
                       'force': True,
                       'extra': ['foo', 'bar'],
                       'expires': date(2014, 10, 15),
                       'lastrun': datetime(2014, 10, 15, 14, 32, 7)})

    complex = Defaults({'home': 'mydata',
                        'processes': 4,
                        'force': True,
                        'extra': ['foo', 'bar'],
                        'mymodule': {'force': False,
                                     'extra': ['foo', 'baz'],
                                     'expires': date(2014, 10, 15),
                                     'arbitrary': {
                                         'nesting': {
                                             'depth': 'works'
                                         }
                                     }
                                 },
                        'extramodule': {'unique': True}})


class TestINIFile(TestINIFileHelper, unittest.TestCase,
                  TestConfigSourceHelper):

    supported_types = (str,)
    supports_nesting = False
    
    def setUp(self):
        super(TestINIFile, self).setUp()
        self.simple = INIFile("simple.ini")
        self.complex = INIFile("complex.ini")

    # Overrides of TestHelper.test_get, .test_typed and
    # .test_subsection_nested due to limitations of INIFile
    # INIFile carries no typing information
    def test_get(self):
        self.assertEqual(self.simple.get("home"), "mydata")
        self.assertEqual(self.simple.get("processes"), "4")
        self.assertEqual(self.simple.get("force"), "True")
        self.assertEqual(self.simple.get("extra"), "foo, bar")
        self.assertEqual(self.simple.get("expires"), "2014-10-15")
        self.assertEqual(self.simple.get("lastrun"), "2014-10-15 14:32:07")

    def test_typed(self):
        for key in self.simple.keys():
            self.assertFalse(self.simple.typed(key))

    # Override: INIFile doesn't support nested subsections
    def test_subsection_nested(self):
        subsec = self.complex.subsection('mymodule')
        self.assertEqual(set(subsec.subsections()),
                         set(()))

    def test_inifile_default_as_root(self):
        # using a rootsection named DEFAULT triggers different
        # cascading-like behaviour in configparser.

        # load a modified version of complex.ini
        with open("complex.ini") as fp:
            ini = fp.read()
            
        with open("complex-otherroot.ini", "w") as fp:
            fp.write(ini.replace("[__root__]", "[DEFAULT]"))
        cfg = LayeredConfig(INIFile("complex-otherroot.ini",
                                    rootsection="DEFAULT"))

        # this is a modified/simplified version of ._test_subsections
        self.assertEqual(cfg.home, 'mydata')
        self.assertEqual(cfg.processes, '4')
        self.assertEqual(cfg.force, 'True')
        self.assertEqual(cfg.mymodule.force, 'False')
        self.assertEqual(cfg.extra, "foo, bar")
        self.assertEqual(cfg.mymodule.extra, "foo, baz")
        with self.assertRaises(AttributeError):
            cfg.expires
        self.assertEqual(cfg.mymodule.expires, "2014-10-15")

        # this is really unwanted cascading behaviour
        self.assertEqual(cfg.mymodule.home, 'mydata')
        self.assertEqual(cfg.mymodule.processes, '4')

        os.unlink("complex-otherroot.ini")

    def test_inifile_nonexistent(self):
        logging.getLogger().setLevel(logging.CRITICAL)
        cfg = LayeredConfig(INIFile("nonexistent.ini"))
        self.assertEqual([], list(cfg))

        # make sure a nonexistent inifile doesn't interfere with the
        # rest of the LayeredConfig object
        defobj = Defaults({'datadir': 'something'})
        iniobj = INIFile("nonexistent.ini")
        cfg = LayeredConfig(defobj, iniobj)
        self.assertEqual("something", cfg.datadir)

        # and make sure it's settable (should set up the INIFile
        # object and affect it, and leave the defaults dict untouched
        # as it's the lowest priority)
        cfg.datadir = "else"
        self.assertEqual("else", cfg.datadir)
        self.assertEqual("else", iniobj.get("datadir"))
        self.assertEqual("something", defobj.get("datadir"))

        # same as above, but with a "empty" INIFile object
        iniobj = INIFile()
        cfg = LayeredConfig(defobj, iniobj)
        self.assertEqual("something", cfg.datadir)
        cfg.datadir = "else"
        self.assertEqual("else", cfg.datadir)

    def test_write(self):
        cfg = LayeredConfig(INIFile("complex.ini"))
        cfg.mymodule.expires = date(2014, 10, 24)
        # calling write for any submodule will force a write of the
        # entire config file
        LayeredConfig.write(cfg.mymodule)
        want = """[__root__]
home = mydata
processes = 4
force = True
extra = foo, bar

[mymodule]
force = False
extra = foo, baz
expires = 2014-10-24

[extramodule]
unique = True

"""
        with open("complex.ini") as fp:
            got = fp.read().replace("\r\n", "\n")
        self.assertEqual(want, got)


class TestJSONFile(unittest.TestCase, TestConfigSourceHelper):

    supported_types = (str, int, bool, list)
    
    def setUp(self):
        with open("simple.json", "w") as fp:
            fp.write("""
{"home": "mydata",
 "processes": 4,
 "force": true,
 "extra": ["foo", "bar"],
 "expires": "2014-10-15",
 "lastrun": "2014-10-15 14:32:07"}
""")

        with open("complex.json", "w") as fp:
            fp.write("""
{"home": "mydata",
 "processes": 4,
 "force": true,
 "extra": ["foo", "bar"],
 "mymodule": {"force": false,
              "extra": ["foo", "baz"],
              "expires": "2014-10-15",
              "arbitrary": {
                  "nesting": {
                      "depth": "works"
                  }
              }
          },
 "extramodule": {"unique": true}
}
""")
        self.simple = JSONFile("simple.json")
        self.complex = JSONFile("complex.json")

    def tearDown(self):
        os.unlink("simple.json")
        os.unlink("complex.json")

    def test_get(self):
        self.assertEqual(self.simple.get("home"), "mydata")
        self.assertEqual(self.simple.get("processes"), 4)
        self.assertEqual(self.simple.get("force"), True)
        self.assertEqual(self.simple.get("extra"), ['foo', 'bar'])
        self.assertEqual(self.simple.get("expires"), "2014-10-15")
        self.assertEqual(self.simple.get("lastrun"), "2014-10-15 14:32:07")

    def test_typed(self):
        for key in self.simple.keys():
            # JSON can type ints, bools and lists
            if key in ("processes", "force", "extra"):
                self.assertTrue(self.simple.typed(key))
            else:
                self.assertFalse(self.simple.typed(key))

    def test_write(self):
        self.maxDiff = None
        cfg = LayeredConfig(self.complex)
        cfg.mymodule.expires = date(2014, 10, 24)
        # calling write for any submodule will force a write of the
        # entire config file
        LayeredConfig.write(cfg.mymodule)
        want = """{
    "extra": [
        "foo",
        "bar"
    ],
    "extramodule": {
        "unique": true
    },
    "force": true,
    "home": "mydata",
    "mymodule": {
        "arbitrary": {
            "nesting": {
                "depth": "works"
            }
        },
        "expires": "2014-10-24",
        "extra": [
            "foo",
            "baz"
        ],
        "force": false
    },
    "processes": 4
}"""
        with open("complex.json") as fp:
            got = fp.read().replace("\r\n", "\n")
        self.assertEqual(want, got)

class TestYAMLFile(unittest.TestCase,
                   TestConfigSourceHelper):
    def setUp(self):
        with open("simple.yaml", "w") as fp:
            fp.write("""
home: mydata
processes: 4
force: true
extra: 
- foo
- bar
expires: 2014-10-15
lastrun: 2014-10-15 14:32:07
""")
        with open("complex.yaml", "w") as fp:
            fp.write("""
home: mydata
processes: 4
force: true
extra:
- foo
- bar
mymodule:
    force: false
    extra:
    - foo
    - baz
    expires: 2014-10-15
    arbitrary:
        nesting:
            depth: works
extramodule:
    unique: true
""")
        self.simple = YAMLFile("simple.yaml")
        self.complex = YAMLFile("complex.yaml")

    def tearDown(self):
        os.unlink("simple.yaml")
        os.unlink("complex.yaml")

    # Also, strings are unicode when they need to be,
    # str otherwise.
    def test_i18n(self):
        with codecs.open("i18n.yaml", "w", encoding="utf-8") as fp:
            fp.write("shrimpsandwich: Räksmörgås")
        cfg = LayeredConfig(YAMLFile("i18n.yaml"))
        self.assertEqual("Räksmörgås", cfg.shrimpsandwich)
        os.unlink("i18n.yaml")

    def test_write(self):
        cfg = LayeredConfig(self.complex)
        cfg.mymodule.expires = date(2014, 10, 24)
        # calling write for any submodule will force a write of the
        # entire config file
        LayeredConfig.write(cfg.mymodule)
        # note that pyyaml sorts keys alphabetically and has specific
        # ideas on how to format the result (controllable through
        # mostly-undocumented args to dump())
        want = """
extra:
- foo
- bar
extramodule:
  unique: true
force: true
home: mydata
mymodule:
  arbitrary:
    nesting:
      depth: works
  expires: 2014-10-24
  extra:
  - foo
  - baz
  force: false
processes: 4
""".lstrip()
        with open("complex.yaml") as fp:
            got = fp.read().replace("\r\n", "\n")
        self.assertEqual(want, got)

class TestPListFile(unittest.TestCase, TestConfigSourceHelper):

    supported_types = (str, int, bool, list, datetime)

    def setUp(self):
        with open("simple.plist", "w") as fp:
            fp.write("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>expires</key>
        <string>2014-10-15</string>
        <key>extra</key>
        <array>
                <string>foo</string>
                <string>bar</string>
        </array>
        <key>force</key>
        <true/>
        <key>home</key>
        <string>mydata</string>
        <key>lastrun</key>
        <date>2014-10-15T14:32:07Z</date>
        <key>processes</key>
        <integer>4</integer>
</dict>
</plist>
""")
        with open("complex.plist", "w") as fp:
            fp.write("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
        <key>extra</key>
        <array>
                <string>foo</string>
                <string>bar</string>
        </array>
        <key>extramodule</key>
        <dict>
                <key>unique</key>
                <true/>
        </dict>
        <key>force</key>
        <true/>
        <key>home</key>
        <string>mydata</string>
        <key>mymodule</key>
        <dict>
                <key>arbitrary</key>
                <dict>
                        <key>nesting</key>
                        <dict>
                                <key>depth</key>
                                <string>works</string>
                        </dict>
                </dict>
                <key>expires</key>
                <string>2014-10-15</string>
                <key>extra</key>
                <array>
                        <string>foo</string>
                        <string>baz</string>
                </array>
                <key>force</key>
                <false/>
        </dict>
        <key>processes</key>
        <integer>4</integer>
</dict>
</plist>
""")
        self.simple = PListFile("simple.plist")
        self.complex = PListFile("complex.plist")

    def tearDown(self):
        os.unlink("simple.plist")
        os.unlink("complex.plist")

    # override only because plists cannot handle date objects (only datetime)
    def test_get(self):
        self.assertEqual(self.simple.get("home"), "mydata")
        self.assertEqual(self.simple.get("processes"), 4)
        self.assertEqual(self.simple.get("force"), True)
        self.assertEqual(self.simple.get("extra"), ['foo', 'bar'])
        self.assertEqual(self.simple.get("expires"), "2014-10-15")
        self.assertEqual(self.simple.get("lastrun"),
                         datetime(2014, 10, 15, 14, 32, 7))

    def test_write(self):
        self.maxDiff = None
        cfg = LayeredConfig(self.complex)
        cfg.mymodule.expires = date(2014, 10, 24)
        # calling write for any submodule will force a write of the
        # entire config file
        LayeredConfig.write(cfg.mymodule)
        # note: plistlib creates files with tabs, not spaces.
        want = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>extra</key>
	<array>
		<string>foo</string>
		<string>bar</string>
	</array>
	<key>extramodule</key>
	<dict>
		<key>unique</key>
		<true/>
	</dict>
	<key>force</key>
	<true/>
	<key>home</key>
	<string>mydata</string>
	<key>mymodule</key>
	<dict>
		<key>arbitrary</key>
		<dict>
			<key>nesting</key>
			<dict>
				<key>depth</key>
				<string>works</string>
			</dict>
		</dict>
		<key>expires</key>
		<string>2014-10-24</string>
		<key>extra</key>
		<array>
			<string>foo</string>
			<string>baz</string>
		</array>
		<key>force</key>
		<false/>
	</dict>
	<key>processes</key>
	<integer>4</integer>
</dict>
</plist>
"""
        if sys.version_info < (2,7,0): # pragma: no cover
            # on py26, the doctype includes "Apple Computer" not "Apple"...
            want = want.replace("//Apple//", "//Apple Computer//")
        with open("complex.plist") as fp:
            got = fp.read().replace("\r\n", "\n")
        self.assertEqual(want, got)


class TestCommandline(unittest.TestCase, TestConfigSourceHelper):

    # Note: bool is "half-way" supported. Only value-less parameters
    # are typed as bool (eg "--force", not "--force=True")
    supported_types = (str, list, bool)

    simple_cmdline = ['--home=mydata',
                      '--processes=4',
                      '--force',  # note implicit boolean typing
                      '--extra=foo',
                      '--extra=bar',
                      '--expires=2014-10-15',
                      '--lastrun=2014-10-15 14:32:07']

    complex_cmdline = ['--home=mydata',
                       '--processes=4',
                       '--force=True',
                       '--extra=foo',
                       '--extra=bar',
                       '--mymodule-force=False',
                       '--mymodule-extra=foo',
                       '--mymodule-extra=baz',
                       '--mymodule-expires=2014-10-15',
                       '--mymodule-arbitrary-nesting-depth=works',
                       '--extramodule-unique']

    def setUp(self):
        super(TestCommandline, self).setUp()
        # this means we lack typing information
        self.simple = Commandline(self.simple_cmdline)
        self.complex = Commandline(self.complex_cmdline)


    # Overrides of TestHelper.test_get, .test_typed and and due to
    # limitations of Commandline (carries almost no typeinfo)
    def test_get(self):
        self.assertEqual(self.simple.get("home"), "mydata")
        self.assertEqual(self.simple.get("processes"), "4")
        self.assertEqual(self.simple.get("force"), True)
        self.assertEqual(self.simple.get("extra"), ['foo','bar']) # note typed!
        self.assertEqual(self.simple.get("expires"), "2014-10-15")
        self.assertEqual(self.simple.get("lastrun"), "2014-10-15 14:32:07")

    def test_typed(self):
        for key in self.simple.keys():
            # these should be typed as bool and list, respectively
            if key in ("force", "extra"):
                self.assertTrue(self.simple.typed(key))
            else:
                self.assertFalse(self.simple.typed(key))                

    def test_config_subsections(self):
        # this case uses valued parameter for --force et al, which
        # cannot be reliably converted to bools using only intrinsic
        # information
        self.supported_types = (str, list)
        super(TestCommandline, self).test_config_subsections()


class TestCommandlineConfigured(TestCommandline):

    supported_types = (str, int, bool, date, datetime, list)
    
    def setUp(self):
        super(TestCommandlineConfigured, self).setUp()
        simp = argparse.ArgumentParser(description="This is a simple program")
        simp.add_argument('--home', help="The home directory of the app")
        simp.add_argument('--processes', type=int, help="Number of simultaneous processes")
        simp.add_argument('--force', type=LayeredConfig.boolconvert, nargs='?', const=True)
        simp.add_argument('--extra', action='append')
        simp.add_argument('--expires', type=LayeredConfig.dateconvert)
        simp.add_argument('--lastrun', type=LayeredConfig.datetimeconvert)
        simp.add_argument('--unused')
        self.simple = Commandline(self.simple_cmdline,
                                  parser=simp)

        comp = argparse.ArgumentParser(description="This is a complex program")
        comp.add_argument('--home', help="The home directory of the app")
        comp.add_argument('--processes', type=int, help="Number of simultaneous processes")
        comp.add_argument('--force', type=LayeredConfig.boolconvert, nargs='?', const=True)
        comp.add_argument('--extra', action='append')
        comp.add_argument('--mymodule-force', type=LayeredConfig.boolconvert, nargs='?', const=True)
        comp.add_argument('--mymodule-extra', action='append')
        comp.add_argument('--mymodule-expires', type=LayeredConfig.dateconvert)
        comp.add_argument('--mymodule-arbitrary-nesting-depth')
        comp.add_argument('--extramodule-unique', nargs='?', const=True)
        self.complex = Commandline(self.complex_cmdline,
                                   parser=comp)

    def test_get(self):
        # re-enable the original impl of test_get
        TestConfigSourceHelper.test_get(self)

    def test_config_subsections(self):
        # re-enable the original impl of test_config_subsections
        TestConfigSourceHelper.test_config_subsections(self)


class TestEnvironment(unittest.TestCase, TestConfigSourceHelper):

    supported_types = (str,)
    
    simple = Environment({'MYAPP_HOME': 'mydata',
                          'MYAPP_PROCESSES': '4',
                          'MYAPP_FORCE': 'True',
                          'MYAPP_EXTRA': 'foo, bar',
                          'MYAPP_EXPIRES': '2014-10-15',
                          'MYAPP_LASTRUN': '2014-10-15 14:32:07'},
                         prefix="MYAPP_")
    complex = Environment({'MYAPP_HOME': 'mydata',
                           'MYAPP_PROCESSES': '4',
                           'MYAPP_FORCE': 'True',
                           'MYAPP_EXTRA': 'foo, bar',
                           'MYAPP_MYMODULE_FORCE': 'False',
                           'MYAPP_MYMODULE_EXTRA': 'foo, baz',
                           'MYAPP_MYMODULE_EXPIRES': '2014-10-15',
                           'MYAPP_MYMODULE_ARBITRARY_NESTING_DEPTH': 'works',
                           'MYAPP_EXTRAMODULE_UNIQUE': 'True'},
                          prefix="MYAPP_")

    def test_get(self):
        self.assertEqual(self.simple.get("home"), "mydata")
        self.assertEqual(self.simple.get("processes"), "4")
        self.assertEqual(self.simple.get("force"), "True")
        self.assertEqual(self.simple.get("extra"), "foo, bar")
        self.assertEqual(self.simple.get("expires"), "2014-10-15")
        self.assertEqual(self.simple.get("lastrun"), "2014-10-15 14:32:07")

    def test_typed(self):
        for key in self.simple.keys():
            self.assertFalse(self.simple.typed(key))


class TestTyping(unittest.TestCase):
    types = {'home': str,
             'processes': int,
             'force': bool,
             'extra': list,
             'mymodule': {'force': bool,
                          'extra': list,
                          'expires': date,
                          'lastrun': datetime,
                      }
             }

    def test_typed_commandline(self):
        cmdline = ['--home=mydata',
                   '--processes=4',
                   '--force=True',
                   '--extra=foo',
                   '--extra=bar',
                   '--implicitboolean',
                   '--mymodule-force=False',
                   '--mymodule-extra=foo',
                   '--mymodule-extra=baz',
                   '--mymodule-expires=2014-10-15',
                   '--mymodule-arbitrary-nesting-depth=works',
                   '--extramodule-unique']
        cfg = LayeredConfig(Defaults(self.types), Commandline(cmdline))
        # FIXME: find a neat way to run the tests in
        # test_config_subsections with a LayeredConfig object that uses a
        # Default object for typing
        TestConfigSourceHelper.test_config_subsections(self, cfg)
        self.assertTrue(cfg.implicitboolean)
        self.assertIs(type(cfg.implicitboolean), bool)

    def test_typed_novalue(self):
        # this cmdline only sets some of the settings. The test is
        # that the rest should raise AttributeError (not return None,
        # as was the previous behaviour), and that __iter__ should not
        # include them.
        cmdline = ['--processes=4', '--force=False']
        cfg = LayeredConfig(Defaults(self.types), Commandline(cmdline))
        self.assertEqual(4, cfg.processes)
        self.assertIsInstance(cfg.processes, int)
        with self.assertRaises(AttributeError):
            cfg.home
        with self.assertRaises(AttributeError):
            cfg.extra
        self.assertEqual(set(['processes', 'force']),
                         set(list(cfg)))

    def test_typed_override(self):
        # make sure this auto-typing isn't run for bools
        types = {'logfile': True}
        cmdline = ["--logfile=out.log"]
        cfg = LayeredConfig(Defaults(types), Commandline(cmdline))
        self.assertEqual(cfg.logfile, "out.log")

    def test_typed_commandline_cascade(self):
        # the test here is that __getattribute__ must determine that
        # subconfig.force is not typed in itself, and fetch type
        # information from the root of defaults

        defaults = {'force': True,
                    'lastdownload': datetime,
                    'mymodule': {}}
        cmdline = ['--mymodule-force=False']
        cfg = LayeredConfig(Defaults(defaults), Commandline(cmdline),
                            cascade=True)
        subconfig = getattr(cfg, 'mymodule')
        self.assertIs(type(subconfig.force), bool)
        self.assertEqual(subconfig.force, False)

        # test typed config values that have no actual value. Since
        # they have no value, they should raise AtttributeError
        with self.assertRaises(AttributeError):
            self.assertEqual(cfg.lastdownload, None)
        with self.assertRaises(AttributeError):
            self.assertEqual(subconfig.lastdownload, None)


class TestTypingINIFile(TestINIFileHelper,
                        unittest.TestCase):
    
    types = {'home': str,
             'processes': int,
             'force': bool,
             'extra': list,
             'mymodule': {'force': bool,
                          'extra': list,
                          'expires': date,
                          'lastrun': datetime,
                      }
             }

    # FIXME: find a neat way to run the tests in
    # test_config_subsections with a LayeredConfig object that uses a
    # Default object for typing
    def test_typed_inifile(self):
        cfg = LayeredConfig(Defaults(self.types), INIFile("complex.ini"))
        self.supported_types = (str, bool, int, list, date, datetime)
        self.supports_nesting = False
        TestConfigSourceHelper.test_config_subsections(self, cfg)


class TestLayered(TestINIFileHelper, unittest.TestCase):
    def test_layered(self):
        defaults = {'home': 'someplace'}
        cmdline = ['--home=anotherplace']
        env = {'MYAPP_HOME': 'yourdata'}
        cfg = LayeredConfig(Defaults(defaults))
        self.assertEqual(cfg.home, 'someplace')
        cfg = LayeredConfig(Defaults(defaults), INIFile("simple.ini"))
        self.assertEqual(cfg.home, 'mydata')
        cfg = LayeredConfig(Defaults(defaults), INIFile("simple.ini"),
                            Environment(env, prefix="MYAPP_"))
        self.assertEqual(cfg.home, 'yourdata')
        cfg = LayeredConfig(Defaults(defaults), INIFile("simple.ini"),
                            Environment(env, prefix="MYAPP_"),
                            Commandline(cmdline))
        self.assertEqual(cfg.home, 'anotherplace')
        self.assertEqual(['home', 'processes', 'force', 'extra', 'expires',
                          'lastrun'], list(cfg))

    def test_layered_subsections(self):
        defaults = OrderedDict((('force', False),
                                ('home', 'thisdata'),
                                ('loglevel', 'INFO')))
        cmdline = ['--mymodule-home=thatdata', '--mymodule-force']
        cfg = LayeredConfig(Defaults(defaults), Commandline(cmdline),
                            cascade=True)
        self.assertEqual(cfg.mymodule.force, True)
        self.assertEqual(cfg.mymodule.home, 'thatdata')
        self.assertEqual(cfg.mymodule.loglevel, 'INFO')

        # second test is more difficult: the lower-priority Defaults
        # source only contains a subsection, while the higher-priority
        # Commandline source contains no such subsection. Our
        # sub-LayeredConfig object will only have a Defaults source,
        # not a Commandline source (which will cause the
        # __getattribute__ lookup_resource to look in the Defaults
        # object in the sub-LayeredConfig object, unless we do
        # something smart.
        defaults = {'mymodule': defaults}
        cmdline = ['--home=thatdata', '--force']

        o = Commandline(cmdline)
        o.subsection("mymodule").keys()
        cfg = LayeredConfig(Defaults(defaults), Commandline(cmdline),
                            cascade=True)
        self.assertEqual(cfg.mymodule.force, True)
        self.assertEqual(cfg.mymodule.home, 'thatdata')
        self.assertEqual(cfg.mymodule.loglevel, 'INFO')
        self.assertEqual(['force', 'home', 'loglevel'], list(cfg.mymodule))



class TestSubsections(unittest.TestCase):
    def test_list(self):
        defaults = {'home': 'mydata',
                    'subsection': {'processes': 4}}
        cfg = LayeredConfig(Defaults(defaults),
                            cascade=True)
        self.assertEqual(set(['home', 'processes']),
                         set(cfg.subsection))


class TestModifications(TestINIFileHelper, unittest.TestCase):
    def test_modified(self):
        defaults = {'lastdownload': None}
        cfg = LayeredConfig(Defaults(defaults))
        now = datetime.now()
        cfg.lastdownload = now
        self.assertEqual(cfg.lastdownload, now)

    def test_modified_subsections(self):
        defaults = {'force': False,
                    'home': 'thisdata',
                    'loglevel': 'INFO'}
        cmdline = ['--mymodule-home=thatdata', '--mymodule-force']
        cfg = LayeredConfig(Defaults(defaults),
                            INIFile("complex.ini"),
                            Commandline(cmdline),
                            cascade=True)
        cfg.mymodule.expires = date(2014, 10, 24)

    def test_modified_singlesource_subsection(self):
        self.globalconf = LayeredConfig(
            Defaults({'download_text': None,
                      'base': {}}),
            cascade=True)
        # this should't raise an AttributeError
        self.globalconf.base.download_text
        # this shouldn't, either
        self.globalconf.base.download_text = "WHAT"

        

    def test_write_noconfigfile(self):
        cfg = LayeredConfig(Defaults({'lastrun':
                                      datetime(2012, 9, 18, 15, 41, 0)}))
        cfg.lastrun = datetime(2013, 9, 18, 15, 41, 0)
        LayeredConfig.write(cfg)

    def test_set_novalue(self):
        # it should be possible to set values that are defined in any
        # of the configsources, even though only typing information
        # exists there.
        cfg = LayeredConfig(Defaults({'placeholder': int}),
                            Commandline([]))
        cfg.placeholder = 42

        # but it shouldn't be possible to set values that hasn't been
        # defined anywhere.
        with self.assertRaises(AttributeError):
            cfg.nonexistent = 43


class TestAccessors(TestINIFileHelper, unittest.TestCase):

    def test_set(self):
        # a value is set in a particular underlying source, and the
        # dirty flag isn't set.
        cfg = LayeredConfig(INIFile("simple.ini"))
        LayeredConfig.set(cfg, 'expires', date(2013, 9, 18),
                          "inifile")
        # NOTE: For this config, where no type information is
        # available for key 'expires', INIFile.set will convert the
        # date object to a string, at which point typing is lost.
        # Therefore this commmented-out test will fail
        # self.assertEqual(date(2013, 9, 18), cfg.expires)
        self.assertEqual("2013-09-18", cfg.expires)
        self.assertFalse(cfg._sources[0].dirty)

    def test_get(self):
        cfg = LayeredConfig(Defaults({'codedefaults': 'yes',
                                      'force': False,
                                      'home': '/usr/home'}),
                            INIFile('simple.ini'))
        # and then do a bunch of get() calls with optional fallbacks
        self.assertEqual("yes", LayeredConfig.get(cfg, "codedefaults"))
        self.assertEqual("mydata", LayeredConfig.get(cfg, "home"))
        self.assertEqual(None, LayeredConfig.get(cfg, "nonexistent"))
        self.assertEqual("NO!", LayeredConfig.get(cfg, "nonexistent", "NO!"))

if __name__ == '__main__':
    unittest.main()
