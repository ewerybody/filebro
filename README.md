# filebro

# the big picture
Filebro is going to be an easy to use day to day file browser.
From the surface it's going to look lightweight but it offers extensive and
foremost extensible functionality under the hood.
Still it will feel always responsive and snappy.

This already goes into the fundamentally different things. There is always a
background process for filebro. Users should never be blocked on the UI.
Things that take a moment or two are send off to the backend to be worked on in
dedicated processes. If there are multiple CPU heavy things requested it will
try to utilize all the available processors.

Enabling this kind of utilization for as many different tasks imaginable the
implementation of such a task should be super easy and the backend will try to
orchestrate as much as possible.

# first steps
* implement simple CPU heavy task scripts to be controlled with inputs to main() function
* create multi-process scheduler to be kicked off via subprocess from backend
*