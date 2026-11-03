from unittest.mock import patch
from twys import integrations, marketplace, social
import json

def test_no_key_calendar_defaults_to_public_provider():
    payload={"events":[{"id":321,"title":"CPI release","time_utc":"2026-10-16T12:30:00+00:00","impact":"high","consensus":"2.6%","prior":"2.7%","actual":None,"currency":"USD"}]}
    with patch.object(integrations,'config',return_value={'calendar_provider':'financecalendar'}),patch.object(integrations,'fetch',return_value=json.dumps(payload).encode()):
        got=integrations.get_calendar('2026-10-12','2026-10-18')
    assert got['status']=='ok' and got['provider']=='financecalendar'
    assert got['events'][0]['forecast']=='2.6%'
    assert got['events'][0]['datetime'].endswith('+00:00')

def test_calendar_rejects_bad_order():
    with patch.object(integrations,'config',return_value={}):
        got=integrations.get_calendar('2026-10-18','2026-10-12')
    assert got['status']=='error'

def test_reddit_results_filtered_by_exact_pair():
    from datetime import datetime, timezone
    timestamp=datetime.now(timezone.utc).isoformat()
    feed=f"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>EURUSD breakout</title><updated>{timestamp}</updated><link href="https://www.reddit.com/r/Forex/123"/></entry><entry><title>GBPUSD breakout</title><updated>{timestamp}</updated><link href="https://www.reddit.com/r/Forex/456"/></entry></feed>""".encode()
    with patch.object(integrations,'fetch',return_value=feed):got=social.public_commentary('EURUSD')
    assert got['status']=='ok' and len(got['items'])==1
    assert got['items'][0]['title']=='EURUSD breakout'
