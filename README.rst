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

If this plugin has collisions with commands from other plugins in your bot, you can set a command prefix like ``/group_`` for all commands::

  simplebot -a bot@example.com db simplebot_chess/command_prefix group_

Install
-------

To install run::

  pip install simplebot-groups


.. _SimpleBot: https://github.com/simplebot-org/simplebot
