"""Expose bounded JUnit failures as check annotations, without downloading logs."""
from pathlib import Path
import xml.etree.ElementTree as ET


def escape(value):
    return value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


report = Path('python-tests.xml')
if report.is_file():
    for case in ET.parse(report).iter('testcase'):
        for kind in ('failure', 'error'):
            failure = case.find(kind)
            if failure is not None:
                message = (failure.text or failure.get('message') or 'Test failed')[-10000:]
                print('::error::' + escape(case.get('name', 'pytest') + '\n' + message))
