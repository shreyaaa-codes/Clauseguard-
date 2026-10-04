# ClauseGuard Annotation Guide

This guide defines how sentences should be manually labelled for the evaluation dataset.

## Positive Class (Label: 1)
A sentence describing collection, use, sharing, retention, tracking, or another concrete handling of personal/user/device data.

**Examples:**
* "Our servers automatically record your browsing history."
* "We may distribute your email address to our affiliates."
* "GPS coordinates are continuously transmitted to our background service."

## Negative Class (Label: 0)
A sentence that does not describe a data practice. This includes general software instructions, greetings, legal jurisdiction boilerplate, and non-privacy disclaimers.

**Examples:**
* "Please press the confirmation button to proceed."
* "Thank you for installing our software suite."
* "Any disputes will be resolved under the laws of the State of California."
