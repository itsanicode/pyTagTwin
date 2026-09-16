# -*- coding: utf-8 -*-
"""Edit and store the Tag Twin settings."""

from pyrevit import forms

from tagtwin.revit import ui

__title__ = 'Settings'
__author__ = 'Aniket Kesari'
__doc__ = ('What counts as the same element, what gets copied, and how '
           'annotations are positioned. Settings are stored per user.')


def main():
    options = ui.load_options()
    edited = ui.edit_options(options)
    if edited is None:
        return
    ui.save_options(edited)
    forms.alert('Settings saved.\n\nTolerance: {0} ft\nOffsets: {1}'
                .format(edited.position_tolerance, edited.offset_mode),
                title='Tag Twin')


main()
