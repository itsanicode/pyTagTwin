# Tag Twin

**Author:** Aniket Kesari &nbsp;|&nbsp; pyRevit extension `pyTagTwin`

A **pyRevit** extension that finds the identical elements between two views and
replicates the tags and annotations from one onto the other — intelligent
copying rather than plain copy/paste.

The case it is built for: a riser diagram, a typical bathroom suite, a repeated
apartment layout — the same thing drawn twice. One view is fully annotated. The
other has nothing on it, and arranging the tags by hand is an afternoon.

There are two ways to get from one to the other, and they fail differently:

| | **Tag Like View** | **Replicate Annotations** |
| --- | --- | --- |
| What it copies | Tag types and tag *positions* | Every annotation, tags and dimensions and text alike |
| What it needs | The same **kinds** of element in both views | A correct element-to-element **match** between the views |
| Where it works | Views that are similar | Views that are the same thing modelled twice |
| When it fails | A kind of element the reference view never tagged — that one tag is left where it was | No match, so nothing is placed at all |

**Start with Tag Like View.** It lets Revit do the hosting, which Revit is good
at, and does the part Revit does not do — putting every tag where the finished
drawing puts it. Reach for Replicate Annotations when the two views really are
the same suite twice and you also want the dimensions and text.

## What it does

1. **Fingerprints every model element** in both views. A fingerprint is what a
   drafter would look at — category, family and type, MEP system, size, length
   and whether the element runs up or along. It deliberately contains no
   position and no absolute direction, so it survives the second suite being
   somewhere else, turned around, or handed.
2. **Finds the transform** between the two views: how far the second layout was
   moved, whether it was rotated, and whether it was **mirrored** (the
   back-to-back bathroom case). Candidate transforms are generated from the
   rarest elements — a shower valve is a far better anchor than the two hundredth
   identical elbow — scored on how many elements they explain, and then re-fitted
   through every matched pair so small modelling differences do not throw it off.
3. **Pairs the elements one to one**, shortest distance first. Anything left
   over is retried on looser fingerprints, so a branch cut half an inch shorter
   in the second suite still finds its twin instead of being dropped.
4. **Rebuilds the annotations** in the target view, re-hosted onto the matched
   elements.

Then it tells you exactly what it did — per view, per annotation, with a reason
for anything it would not touch.

## What gets copied

| Annotation | How it is rebuilt |
| --- | --- |
| Tags — element, multi-category, material, keynote | Created fresh against the **matched** element, keeping the tag type, orientation, leader and leader elbow. Multi-reference tags (Revit 2022+) keep every reference that has a twin. |
| Dimensions | Each reference is re-pointed at the matched element, so the dimension measures the new elements and updates with them. |
| Spot elevations and spot coordinates | Re-pointed the same way. |
| Text notes | Re-created with the same type, alignment, rotation, wrapping width, rich-text formatting and leaders. |
| Detail lines | Transformed, keeping the line style. |
| Filled regions, revision clouds | Boundary transformed, keeping the type. |
| Annotation symbols (generic annotations) | Placed at the transformed point with the same rotation, and their instance parameters copied. |
| Room and space tags | Re-hosted onto the matched room or space. |

Everything is re-created rather than copied, which is why text in a **mirrored**
suite still reads forwards instead of backwards.

### The two things that make it feel right on a sheet

- **Tags stay put relative to their element.** A tag's position is stored as an
  offset from the element it labels, not as an absolute point. If the second
  suite's valve sits an inch off, the tag moves with it instead of being left
  stranded.
- **View scale is respected.** Annotation offsets and text wrapping widths are
  model distances, so they are scaled by the ratio of the two views' scales.
  Copying from a 1/4" view into a 1/8" view keeps the drawing looking the same.

## Installation

Tag Twin is a **pyRevit extension**, so [pyRevit](https://github.com/pyrevitlabs/pyRevit/releases)
has to be installed first. Revit **2021–2027** are supported.

### From pyRevit (recommended)

1. **pyRevit → Extensions** to open the Extension Manager.
2. Paste into **Git URL**:

   ```
   https://github.com/itsanicode/pyTagTwin.git
   ```

3. Leave **Token** empty — this repository is public — and click **Add and install**.
4. **pyRevit → Reload**. A **Tag Twin** tab appears on the ribbon.

pyRevit clones this repository into
`%APPDATA%\pyRevit\Extensions\pyTagTwin.extension`, which is why the repository
root *is* the extension bundle: `lib/` and `Tag Twin.tab/` sit at the top level
rather than inside a folder. Updating later is a **pyRevit → Update** away,
because the installed extension is a git clone.

### From the zip

For a machine where you would rather not use the Extension Manager:

1. Download **[pyTagTwin.zip](https://github.com/itsanicode/pyTagTwin/raw/main/dist/pyTagTwin.zip)**.
2. **Extract the whole zip** (right-click → *Extract All...*) — the installer
   needs the files kept together.
3. Double-click **`Install Tag Twin.bat`**.
4. Start Revit, or **pyRevit → Reload** if it is already open.

The installer copies the extension into `%APPDATA%\pyRevit\Extensions` — no
administrator rights, nothing outside your user profile. To remove it, run
**`Uninstall Tag Twin.bat`**. Running the same installer from a clone of this
repository works too, and installs only the parts Revit loads.

## Usage

### Tag Like View

The path that does not depend on the two views matching up.

1. **Open the view that is already tagged** the way you want. Working on the
   sheet is fine — Tag Twin resolves a sheet to the view placed on it, and asks
   which one when there is more than one.
2. **Tag Twin → Tag Like View**.
3. Pick the views to tag. Read what it learned, then confirm.

It does three things, and the fragile step is simply absent:

1. **Learns** the arrangement of the open view — for every tag, which tag type
   it is and how far it sits from its element, measured along the view's own
   right and up axes.
2. **Tags** whatever is untagged in the target view, using the tag type the
   reference view uses for that category. This is Revit's *Tag All*, except the
   tag type comes from the drawing you are copying rather than from a dialog,
   and existing tags are left alone rather than duplicated.
3. **Arranges** every tag onto the learned offset.

Nowhere does it need to know that pipe #4021 in one view is pipe #8894 in the
other. It only needs both views to contain the same *kinds* of element, so the
target view can be a different size, a different suite, or a different building
entirely.

**Staggering is preserved.** Three identical valves tagged at three different
offsets so their tags do not collide are stored in the order they appear in the
view, and replayed in that order onto the target view's valves — read top to
bottom, then left to right, in both views. If the target has more of them, the
pattern repeats rather than piling every extra tag onto the last offset.

**When a kind of element was never tagged** in the reference view, Tag Twin
falls back to the typical offset for that category, and says so in the report.
If the category is unknown too, the tag is left where Revit put it and listed.

How alike two elements must be to share a tag position is looser than element
matching needs to be — the question is only "does this kind of thing get its tag
up and to the left". The default is the exact signature; drop it to *type and
system* in the settings if a view tags several sizes of the same pipe the same
way.

### Replicate Annotations

1. **Open the annotated view** — the one you want to copy *from*.
2. **Tag Twin → Replicate Annotations**.
3. Pick the target views. Views of the same type are listed first.
4. Read the match report that appears, then confirm.

The report shows, per view, what would actually be copied before anything is
written:

| Column | Meaning |
| --- | --- |
| **Annotations** | How many of the source annotations have a matched element to hang on. **This is what decides whether a run does anything.** |
| **Tagged elements** | The share of the elements that carry an annotation which found a twin. The figure that predicts success. |
| **All elements / Coverage** | Every model element in the view, tagged or not. Background information only. |
| **Match** | excellent / good / partial / poor — a description of how alike the two views are, not a verdict on whether to run. |

A view is run whenever **one or more annotations can be placed**, whatever the
overall coverage says. A riser diagram is mostly bare pipework that nobody tags,
so *Coverage* routinely reads low on a view whose every tag copies across
perfectly — refusing on that number would be refusing the job the tool exists to
do. When nothing can be placed, the message says which of the three usual causes
it was rather than just declining.

A whole run is one undo step.

### Preview Match

The same analysis with nothing written to the model. Use it to see *why* two
views did not pair up: it lists the elements that matched only on a looser
fingerprint, the ones with more than one equally good candidate, and the ones
with no twin at all — every id clickable straight into the model.

### Find Identical

Select an element, run it, and every element in the view with the same
fingerprint is selected. Three strictness levels — exact, same type and system,
same type only. This is the same fingerprint the view matching uses, so it is
the quickest way to understand a disappointing match.

### Settings

What counts as the same element, what gets copied, and how annotations are
positioned. Stored per user by pyRevit.

| Setting | Default | What it does |
| --- | --- | --- |
| Match mirrored (handed) layouts | on | Allows a reflected transform. Turn it off if the model has genuinely symmetric geometry that could pair up the wrong way. |
| Match rotated layouts | on | Allows a rotation about Z. Off is faster when everything is only ever copied straight. |
| Fall back to looser matching | on | Retries unmatched elements ignoring size and length, then ignoring everything but the type. |
| Keep tags at the same offset from their element | on | Positions tags relative to their host rather than absolutely. |
| Adjust for the view scale | on | Scales offsets and text widths by the ratio of the two views' scales. |
| Skip annotations that are already there | on | Makes re-running a view safe — an element that already carries that tag is left alone. |
| Lock target 3D views automatically | off | Revit only allows tags in a **locked** 3D view. With this on, Tag Twin locks the target view for you. |
| Matching tolerance | 0.02 ft (≈6 mm) | How far apart two elements may be and still count as the same one. Raise it when the second layout was modelled by hand rather than copied. |
| Offsets | auto | `auto` keeps offsets in model space for views that look the same way, and in view space otherwise. `model` and `view` force one or the other. |

## How the matching works

The engine is deliberately kept away from the Revit API — it works on plain
records — which is why it can be tested outside Revit and why the fingerprints
are what they are.

**Fingerprints are transform-invariant.** A fingerprint containing a position or
an absolute direction would be useless: the transform is exactly what is being
searched for. So a fingerprint holds category, type, system, size, length and an
orientation class (vertical / horizontal / sloped / point), all of which survive
a move, a rotation about Z and a mirror.

**Three levels, tried in turn:**

| Level | Contains | Used for |
| --- | --- | --- |
| exact | category, type, system, size, length, orientation | anchors, and the first matching pass |
| same type + system | category, type, system, orientation | elements whose size or length differs slightly |
| same type | category, type | last resort, within the same tolerance |

**Finding the transform** is a small RANSAC. One matched pair gives a
translation; two give a rotation, tried with and without a mirror. Candidates
come from the rarest fingerprints first, because a fingerprint with two
candidates can produce far fewer wrong answers than one with two hundred. Every
hypothesis is scored by how many elements it explains — against a
signature-balanced *sample* of the view, so ranking thousands of hypotheses
stays cheap — and the handful of finalists are then re-scored against every
element. A hypothesis that explains the whole view ends the search immediately.

**Refinement.** Once there is a pairing, the transform is re-fitted by least
squares through all matched pairs and everything is matched again, the way ICP
tightens a point-cloud registration. Fitted angles that land within half a
degree of a right angle are snapped, because buildings are drawn on right
angles and a least-squares fit drifts.

**Re-hosting** is the part that makes the copy intelligent. A tag does not store
a point, it stores a *reference* — "the centreline of element 346189", "face 2
of element 149094". A reference serialises to a stable representation that
starts with its element id:

```
346189                              a whole element
346189:0:SURFACE                    a face of a system family
346189:0:INSTANCE:149094:2:SURFACE  a face inside a family instance
```

Swapping the leading id for the matched element's id and parsing the result
gives the same reference **on the twin**. The tail addresses geometry inside the
family, so it stays valid as long as both elements are the same type — which is
the premise of the whole tool. A tag may fall back to a plain whole-element
reference if that fails; a dimension may not, because it measures to a specific
face and would silently move.

## Notes and limits

- **Tags in a 3D view need the view locked.** That is Revit's rule, not Tag
  Twin's: tags and dimensions can only be placed in a 3D view that has had
  *Save Orientation and Lock View* applied. Tag Twin says so plainly rather than
  failing, and can lock the target view for you (settings).
- **Both views must be in the same document.** References into a linked model
  cannot be re-pointed inside your file, and are reported as skipped.
- **The two views should look the same way.** Model-space offsets are exact for
  parallel views. When the views look different ways, offsets are carried in
  view coordinates instead, which keeps the drawing sensible but is an
  approximation.
- **Genuinely symmetric layouts are ambiguous.** If a suite is symmetric, more
  than one transform explains it equally well. That is reported — the confidence
  drops and *Preview Match* names the elements with more than one candidate.
- **Annotations Tag Twin does not rebuild** (detail groups, legend components,
  images, view references) are listed as unsupported in the report rather than
  being copied badly.
- **Nothing is deleted.** Tag Twin only adds. With *skip existing* on, running
  the same view twice adds nothing the second time.
- A run is wrapped in one transaction group, so a whole run is a single undo.

## Repository layout

The repository root is the extension bundle itself, so that pyRevit can clone it
straight into `pyTagTwin.extension`. Everything Revit loads is at the top level;
the rest is development scaffolding that pyRevit ignores.

```
extension.json                 what the Extension Manager shows
lib/tagtwin/                   the engine
  geom.py  signature.py  spatial.py  align.py  matching.py   pure Python, no Revit
  layout.py  outlook.py  options.py  results.py              pure Python, no Revit
  revit/                       everything that touches the Revit API
Tag Twin.tab/Replicate.panel/  the five ribbon buttons
installer/                     install / uninstall without the Extension Manager
dist/pyTagTwin.zip             the download - built from the folders above
tests/                         the test suite - runs without Revit
tools/make_icons.py            regenerates the ribbon icons
tools/make_package.py          rebuilds dist/pyTagTwin.zip
```

## Running the tests

The matching engine has no Revit dependency, so the suite runs on plain Python
(2.7 or 3.x), with no test runner to install:

```bash
python tests/run_tests.py -v
```

`dist/pyTagTwin.zip` is built deterministically, and the suite fails if it is
stale — change anything in the extension and rebuild it with
`python tools/make_package.py` before committing. The suite also asserts that
the repository root is still a valid extension bundle, since a stray
`*.extension` folder here would quietly break the Extension Manager install.

It covers the transform algebra, fingerprint invariance, and the matching cases
that actually turn up — a suite copied, rotated, mirrored, moved up a floor,
modelled with slop, missing a few elements, or not related at all — plus
reference re-pointing against a stubbed Revit API, and a check that every
shipped file parses as both Python 2 and Python 3 (pyRevit's default engine is
IronPython 2.7).

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| "Tag Twin needs a drawing view" | The active view is a legend, a schedule, or a sheet with nothing on it. Open a plan, section, elevation, 3D or drafting view from the Project Browser. A sheet with views on it is handled for you. |
| The Tag Twin tab does not appear | pyRevit is not installed, or it has not reloaded. Click **pyRevit → Reload**. Check that `%APPDATA%\pyRevit\Extensions\pyTagTwin.extension` exists and holds `lib` and `Tag Twin.tab`. |
| **Add and install** did nothing | Check the install path in the Extension Manager, then look for `pyTagTwin.extension` inside it. If the folder is there but empty, git could not reach GitHub from that machine — use the zip instead. |
| "Revit only allows tags and dimensions in a locked 3D view" | Apply *Save Orientation and Lock View* to the target 3D view, or switch on **Lock target 3D views automatically**. |
| Replicate Annotations will not place anything at all | Use **Tag Like View** instead. It needs no element match, only the same kinds of element, so it is the one to reach for when two views are similar rather than identical. |
| Tag Like View left some tags where they were | The reference view never tagged that kind of element, so there was nothing to learn from. The report lists every one. Tag one of them in the reference view and run it again. |
| "Nothing can be copied" although Preview Match found plenty | The elements that matched are not the ones carrying annotations. Preview Match now lists the annotated elements that have no twin — usually they are simply not visible in the target view, which they must be for a tag to attach. |
| Match reads *poor* but the run works fine | Expected on a riser: coverage counts every pipe and fitting, most of which carry no tag. Look at **Annotations** and **Tagged elements** instead. |
| Everything matched but tags were skipped | Read the reason column. Usually the tagged element is not *visible in the target view* — it has to be, or there is nothing to tag. |
| Tags landed in the wrong place | The two views probably look different ways. Try forcing **Offsets** to `view` in the settings. |
| A mirrored suite matched the wrong way round | A symmetric layout has more than one valid answer. Turn off **Match mirrored layouts** to force the unmirrored one. |
| Dimensions were skipped but tags worked | Dimensions measure to a specific face, and Tag Twin will not fall back to a whole-element reference for them. The two elements are the same type but not the same geometry. |
| The run is slow on a very large view | Matching scales with the number of elements *visible in the view*. Crop the view, or turn off **Match rotated layouts** if nothing is ever rotated. |
