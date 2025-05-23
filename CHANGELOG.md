## v1.0.0 - 2025-05-03 - Long overdue 1.0

Noteworthy Changes:

* Complete removal of SPF record support, records should be transitioned to TXT
  values before updating to this version.

Changes:

* Address pending octoDNS 2.x deprecations, require minimum of 1.5.x
* DNS Made Easy does not support quotes in TXT values, add strict_supports check
  around it w/False work-around.

## v0.0.5 - 2023-08-02 - TXT Record Fixes

* Fix problems when manipulating TXT records with values longer than 255 characters

## v0.0.4 - 2023-07-03 - Bulk Record Create & Delete in Batches

* Records created and deleted via bulk operations have in batches
* User configurable batch size

## v0.0.3 - 2023-06-26 - Bulk Record Create & Delete

* Records can immediately be created within a newly created zone
* Record creation/deletion is done via bulk operations

## v0.0.2 - 2023-03-29 - Root NS support

* Enable Root NS record support for managing the top-level NS records in zones
* Add a user-agent to all API requests

## v0.0.1 - 2022-01-06 - Moving

#### Nothworthy Changes

* Initial extraction of DnsMadeEasyProvider from octoDNS core

#### Stuff

Nothing
