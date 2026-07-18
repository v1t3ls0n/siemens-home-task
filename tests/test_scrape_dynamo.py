"""Offline test of scrape_dynamo's parser against a sample that replicates the
Dynamo page DOM: collaboration-model accordions, focus-area tiles, AND the
'Why join Dynamo?' benefit tiles (same markup, plain-text bullets, no links)
that must NOT be captured as partners.

Run: python -m tests.test_scrape_dynamo   (or: python tests/test_scrape_dynamo.py)
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAMPLE = """
<html><body>
<div class="de-accordion scroll-anchor">
 <h3 class="de-accordion__header"><button class="de-accordion__toggle">
  <span class="de-accordion__focus-target">
   <span class="de-accordion__title">Ecosystem Partners</span></span></button></h3>
 <div class="de-accordion__body" hidden="">
  <div class="de-accordion-group__content de-accordion-group__content-article">
   <div class="columnArticleClass two-layout-bg-white">
    <div class="text-start container multitextblock ">
     <div class="row justify-content-left"><div class="col col-md-8">
      <h3><a target="_blank" href="https://instrumental.com/">Instrumental</a></h3>
      <p><a href="https://instrumental.com/">Instrumental</a> built a Manufacturing AI
         platform. When combined with Teamcenter Quality it supports Siemens' approach.</p>
     </div></div>
     <div class="row justify-content-left"><div class="col col-md-8">
      <h3><a href="https://eur01.safelinks.protection.outlook.com/?url=https%3A%2F%2Fcpbxk04.na1.hubspotlinksfree.com%2Ffoo&data=05">ioTech</a></h3>
      <p>ioTech from Jerusalem develops multi-material additive manufacturing.</p>
     </div></div>
    </div></div></div></div></div>
<div class="de-accordion scroll-anchor">
 <h3 class="de-accordion__header"><button class="de-accordion__toggle">
  <span class="de-accordion__focus-target">
   <span class="de-accordion__title">Who is eligible for Dynamo? </span></span></button></h3>
 <div class="de-accordion__body"><div class="multitextblock"><h3>Should be skipped</h3></div></div>
</div>
<div class="container three-column-tile"><div class="row">
 <div class="col-12 tileHeightAdjust"><div class="tile-flex-wrapper">
  <h3 class="strong tileHeading">Robotics &amp; Automation</h3>
  <div class="tileDescription"><ul>
   <li><a href="https://rtr.ai/">Realtime Robotics</a></li>
   <li><a href="https://percepto.co/">Percepto</a></li></ul></div>
 </div></div>
 <div class="col-12 tileHeightAdjust"><div class="tile-flex-wrapper">
  <h3 class="strong tileHeading">Climate tech</h3></div></div>
 <div class="col-12 tileHeightAdjust"><div class="tile-flex-wrapper">
  <h3 class="strong tileHeading">If you're a start-up</h3>
  <div class="tileDescription"><ul>
   <li>Early product validation and use of Siemens technology</li>
   <li>Access to Siemens' internal network of experts</li></ul></div>
 </div></div>
</div></div>
</body></html>
"""


class FakeResp:
    text = SAMPLE

    def raise_for_status(self):
        pass


with patch("httpx.get", return_value=FakeResp()):
    from scripts.scrape_dynamo import parse_live_page
    partners, focus = parse_live_page()

import json
print(json.dumps({k: v["name"] for k, v in partners.items()}, indent=1))
print("focus:", json.dumps(focus, indent=1))

# accordion partners
assert "instrumental" in partners
assert partners["instrumental"]["models"] == ["Ecosystem Partners"]
assert "Teamcenter" in partners["instrumental"]["description"]
assert partners["iotech"]["url"] is None            # tracking link stripped
assert "shouldbeskipped" not in partners            # FAQ accordion ignored

# focus-area tiles: linked partners captured, empty focus area kept
assert "realtimerobotics" in partners and "percepto" in partners
assert focus["Robotics & Automation"] == ["Realtime Robotics", "Percepto"]
assert "Climate tech" in focus and focus["Climate tech"] == []   # real, empty

# THE REGRESSION GUARD: "Why join Dynamo?" benefit bullets are NOT partners,
# and that tile is not treated as a focus area.
assert "If you're a start-up" not in focus
assert not any("Early product validation" in p["name"] for p in partners.values())
assert not any("internal network of experts" in p["name"] for p in partners.values())

print("\nALL PARSER ASSERTIONS PASSED (incl. benefit-bullet exclusion)")
