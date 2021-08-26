Groups
======

.. image:: https://img.shields.io/pypi/v/simplebot_groups.svg
   :target: https://pypi.org/project/simplebot_groups

.. image:: https://img.shields.io/pypi/pyversions/simplebot_groups.svg
   :target: https://pypi.org/project/simplebot_groups

.. image:: https://pepy.tech/badge/simplebot_groups
   :target: https://pepy.tech/project/simplebot_groups

.. image:: https://img.shields.io/pypi/l/simplebot_groups.svg
   :target: https://pypi.org/project/simplebot_groups

.. image:: https://github.com/adbenitez/simplebot_groups/actions/workflows/python-ci.yml/badge.svg
   :target: https://github.com/adbenitez/simplebot_groups/actions/workflows/python-ci.yml

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black

A `SimpleBot`_ plugin that allows users to join public groups and channels and publish their groups so other can join.


Install
-------

To install run::

  pip install simplebot-groups

Customization
-------------

If this plugin has collisions with commands from other plugins in your bot, you can set a command prefix like ``/group_`` for all commands::

  simplebot -a bot@example.com db -s simplebot_groups/command_prefix group_

To set maximum topic length::

  simplebot -a bot@example.com db -s simplebot_groups/max_topic_size 500

To set maximum file size in channels::

  simplebot -a bot@example.com db -s simplebot_groups/max_file_size 1048576

To show sender address in channels::

  simplebot -a bot@example.com db -s simplebot_groups/show_sender 1

To auto-remove members in public groups after some days of inactivity::

  simplebot -a bot@example.com db -s simplebot_groups/max_inactivity 7

To disable channel creation for non-admins::

  simplebot -a bot@example.com db -s simplebot_groups/allow_channels 0

To disable group publishing for non-admins::

  simplebot -a bot@example.com db -s simplebot_groups/allow_groups 0


.. _SimpleBot: https://github.com/simplebot-org/simplebot
