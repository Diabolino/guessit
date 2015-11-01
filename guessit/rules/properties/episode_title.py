#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Episode title
"""
from collections import defaultdict
from guessit.rules.common import seps, title_seps
from guessit.rules.properties.title import TitleFromPosition, TitleBaseRule
from rebulk import Rebulk, Rule, AppendMatch, RenameMatch

from ..common.formatters import cleanup


class TitleToEpisodeTitle(Rule):
    """
    If multiple different title are found, convert the one following episode number to episodeTitle.
    """
    dependency = TitleFromPosition

    def when(self, matches, context):
        titles = matches.named('title')

        if len(titles) < 2:
            return

        title_groups = defaultdict(list)
        for title in titles:
            title_groups[title.value].append(title)

        episode_titles = []
        main_titles = []
        for title in titles:
            if matches.previous(title, lambda match: match.name == 'episodeNumber'):
                episode_titles.append(title)
            else:
                main_titles.append(title)

        if episode_titles:
            return episode_titles

    def then(self, matches, when_response, context):
        for episode_title in when_response:
            matches.remove(episode_title)
            episode_title.name = 'episodeTitle'
            matches.append(episode_title)


class EpisodeTitleFromPosition(TitleBaseRule):
    """
    Add episode title match in existing matches
    Must run after TitleFromPosition rule.
    """
    dependency = TitleToEpisodeTitle

    def hole_filter(self, hole, matches):
        episode = matches.previous(hole,
                                   lambda previous: any(name in previous.names
                                                        for name in ['episodeNumber', 'episodeDetails',
                                                                     'episodeCount', 'season', 'seasonCount',
                                                                     'date', 'title']),
                                   0)

        crc32 = matches.named('crc32')

        return episode or crc32

    def filepart_filter(self, filepart, matches):
        # Filepart where title was found.
        if matches.range(filepart.start, filepart.end, lambda match: match.name == 'title'):
            return True
        return False

    def is_ignored(self, match):
        if match.name == 'episodeDetails':
            return True
        return super(EpisodeTitleFromPosition, self).is_ignored(match)

    def should_keep(self, match, to_keep, matches, filepart, hole):
        if match.name == 'episodeDetails' and not matches.previous(match, lambda match: match.name == 'season'):
            return True, False  # Keep episodeDetails, but don't crop title.
        return super(EpisodeTitleFromPosition, self).should_keep(match, to_keep, matches, filepart, hole)

    def __init__(self):
        super(EpisodeTitleFromPosition, self).__init__('episodeTitle', ['title'])

    def when(self, matches, context):
        if matches.named('episodeTitle'):
            return
        return super(EpisodeTitleFromPosition, self).when(matches, context)


class AlternativeTitleReplace(Rule):
    """
    If alternateTitle was found and title is next to episodeNumber, season or date, replace it with episodeTitle.
    """
    dependency = EpisodeTitleFromPosition
    consequence = RenameMatch

    def when(self, matches, context):
        if matches.named('episodeTitle'):
            return

        alternative_title = matches.range(predicate=lambda match: match.name == 'alternativeTitle', index=0)
        if alternative_title:
            main_title = matches.chain_before(alternative_title.start, seps=seps,
                                              predicate=lambda match: 'title' in match.tags, index=0)
            if main_title:
                episode = matches.previous(main_title,
                                           lambda previous: any(name in previous.names
                                                                for name in ['episodeNumber', 'episodeDetails',
                                                                             'episodeCount', 'season', 'seasonCount',
                                                                             'date', 'title']),
                                           0)

                crc32 = matches.named('crc32')

                if episode or crc32:
                    return alternative_title

    def then(self, matches, when_response, context):
        matches.remove(when_response)
        when_response.name = 'episodeTitle'
        matches.append(when_response)


class Filepart3EpisodeTitle(Rule):
    """
    If we have at least 3 filepart structured like this:

    Serie name/SO1/E01-episodeTitle.mkv
    AAAAAAAAAA/BBB/CCCCCCCCCCCCCCCCCCCC

    If CCCC contains episodeNumber and BBB contains seasonNumber
    Then title is to be found in AAAA.
    """
    consequence = AppendMatch('title')

    def when(self, matches, context):
        fileparts = matches.markers.named('path')
        if len(fileparts) < 3:
            return

        filename = fileparts[-1]
        directory = fileparts[-2]
        subdirectory = fileparts[-3]

        episode_number = matches.range(filename.start, filename.end, lambda match: match.name == 'episodeNumber', 0)
        if episode_number:
            season = matches.range(directory.start, directory.end, lambda match: match.name == 'season', 0)

            if season:
                hole = matches.holes(subdirectory.start, subdirectory.end,
                                     formatter=cleanup, seps=title_seps, predicate=lambda match: match.value, index=0)
                if hole:
                    return hole


class Filepart2EpisodeTitle(Rule):
    """
    If we have at least 2 filepart structured like this:

    Serie name SO1/E01-episodeTitle.mkv
    AAAAAAAAAAAAA/BBBBBBBBBBBBBBBBBBBBB

    If BBBB contains episodeNumber and AAA contains a hole followed by seasonNumber
    Then title is to be found in AAAA.
    """
    consequence = AppendMatch('title')

    def when(self, matches, context):
        fileparts = matches.markers.named('path')
        if len(fileparts) < 2:
            return

        filename = fileparts[-1]
        directory = fileparts[-2]

        episode_number = matches.range(filename.start, filename.end, lambda match: match.name == 'episodeNumber', 0)
        if episode_number:
            season = matches.range(directory.start, directory.end, lambda match: match.name == 'season', 0)
            if season:
                hole = matches.holes(directory.start, directory.end, formatter=cleanup, seps=title_seps,
                                     predicate=lambda match: match.value, index=0)
                if hole:
                    return hole


EPISODE_TITLE = Rebulk().rules(EpisodeTitleFromPosition,
                               AlternativeTitleReplace,
                               TitleToEpisodeTitle,
                               Filepart3EpisodeTitle,
                               Filepart2EpisodeTitle)
