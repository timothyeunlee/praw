"""PRAW outdated test suite.

The tests in this file do not run on travis.ci and need to each be moved
into a respective test_NAME.py module. Individual test functions that require
network connectivity should be wrapped with a @betamax decorator.

"""

from __future__ import print_function, unicode_literals

import os
import sys
import unittest
from requests.exceptions import HTTPError
from six import text_type
from praw import errors, helpers
from praw.objects import Comment, MoreComments
from .helper import AuthenticatedHelper, flair_diff


class CacheTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()

    def test_cache(self):
        subreddit = self.r.get_subreddit(self.sr)
        title = 'Test Cache: %s' % self.r.modhash
        body = "BODY"
        original_listing = list(subreddit.get_new(limit=5))
        subreddit.submit(title, body)
        new_listing = list(subreddit.get_new(limit=5))
        self.assertEqual(original_listing, new_listing)
        self.disable_cache()
        no_cache_listing = list(subreddit.get_new(limit=5))
        self.assertNotEqual(original_listing, no_cache_listing)

    def test_refresh_subreddit(self):
        self.disable_cache()
        subreddit = self.r.get_subreddit(self.sr)
        new_description = 'Description %s' % self.r.modhash
        subreddit.update_settings(public_description=new_description)
        self.assertNotEqual(new_description, subreddit.public_description)
        subreddit.refresh()
        self.assertEqual(new_description, subreddit.public_description)

    def test_refresh_submission(self):
        self.disable_cache()
        subreddit = self.r.get_subreddit(self.sr)
        submission = next(subreddit.get_top())
        same_submission = self.r.get_submission(submission_id=submission.id)
        if submission.likes:
            submission.downvote()
        else:
            submission.upvote()
        self.assertEqual(submission.likes, same_submission.likes)
        submission.refresh()
        self.assertNotEqual(submission.likes, same_submission.likes)


class EncodingTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()

    def test_author_encoding(self):
        a1 = next(self.r.get_new()).author
        a2 = self.r.get_redditor(text_type(a1))
        self.assertEqual(a1, a2)
        s1 = next(a1.get_submitted())
        s2 = next(a2.get_submitted())
        self.assertEqual(s1, s2)

    def test_unicode_comment(self):
        sub = next(self.r.get_subreddit(self.sr).get_new())
        text = 'Have some unicode: (\xd0, \xdd)'
        comment = sub.add_comment(text)
        self.assertEqual(text, comment.body)

    def test_unicode_submission(self):
        unique = self.r.modhash
        title = 'Wiki Entry on \xC3\x9C'
        url = 'http://en.wikipedia.org/wiki/\xC3\x9C?id=%s' % unique
        submission = self.r.submit(self.sr, title, url=url)
        self.assertTrue(title in text_type(submission))
        self.assertEqual(title, submission.title)
        self.assertEqual(url, submission.url)


class MoreCommentsTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()
        self.submission = self.r.get_submission(url=self.more_comments_url,
                                                comment_limit=130)

    def test_all_comments(self):
        c_len = len(self.submission.comments)
        flat = helpers.flatten_tree(self.submission.comments)
        continue_items = [x for x in flat if isinstance(x, MoreComments) and
                          x.count == 0]
        self.assertTrue(continue_items)
        cf_len = len(flat)
        saved = self.submission.replace_more_comments(threshold=2)
        ac_len = len(self.submission.comments)
        flat = helpers.flatten_tree(self.submission.comments)
        acf_len = len(flat)
        for item in continue_items:
            self.assertTrue(item.id in [x.id for x in flat])

        self.assertEqual(len(self.submission._comments_by_id), acf_len)
        self.assertTrue(c_len < ac_len)
        self.assertTrue(c_len < cf_len)
        self.assertTrue(ac_len < acf_len)
        self.assertTrue(cf_len < acf_len)
        self.assertTrue(saved)

    def test_comments_method(self):
        predicate = lambda item: isinstance(item, MoreComments)
        item = self.first(self.submission.comments, predicate)
        self.assertTrue(item.comments())


class SaveableTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()

    def _helper(self, item):
        def save():
            item.save()
            item.refresh()
            self.assertTrue(item.saved)
            self.first(self.r.user.get_saved(params={'uniq': item.id}),
                       lambda x: x == item)

        def unsave():
            item.unsave()
            item.refresh()
            self.assertFalse(item.saved)

        if item.saved:
            unsave()
            save()
        else:
            save()
            unsave()

    def test_comment(self):
        self._helper(next(self.r.user.get_comments()))

    def test_submission(self):
        self._helper(next(self.r.user.get_submitted()))


class CommentEditTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()

    def test_reply(self):
        comment = next(self.r.user.get_comments())
        new_body = '%s\n\n+Edit Text' % comment.body
        comment = comment.edit(new_body)
        self.assertEqual(comment.body, new_body)


class CommentPermalinkTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()

    def test_inbox_permalink(self):
        predicate = lambda item: isinstance(item, Comment)
        item = self.first(self.r.get_inbox(), predicate)
        self.assertTrue(item.id in item.permalink)

    def test_user_comments_permalink(self):
        item = next(self.r.user.get_comments())
        self.assertTrue(item.id in item.permalink)

    def test_get_comments_permalink(self):
        sub = self.r.get_subreddit(self.sr)
        item = next(sub.get_comments())
        self.assertTrue(item.id in item.permalink)


class CommentReplyTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()
        self.subreddit = self.r.get_subreddit(self.sr)

    def test_add_comment_and_verify(self):
        text = 'Unique comment: %s' % self.r.modhash
        submission = next(self.subreddit.get_new())
        comment = submission.add_comment(text)
        self.assertEqual(comment.submission, submission)
        self.assertEqual(comment.body, text)

    def test_add_reply_and_verify(self):
        text = 'Unique reply: %s' % self.r.modhash
        predicate = lambda submission: submission.num_comments > 0
        submission = self.first(self.subreddit.get_new(), predicate)
        comment = submission.comments[0]
        reply = comment.reply(text)
        self.assertEqual(reply.parent_id, comment.fullname)
        self.assertEqual(reply.body, text)


class CommentReplyNoneTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()

    def test_front_page_comment_replies_are_none(self):
        item = next(self.r.get_comments('all'))
        self.assertEqual(item._replies, None)

    def test_inbox_comment_replies_are_none(self):
        predicate = lambda item: isinstance(item, Comment)
        comment = self.first(self.r.get_inbox(), predicate)
        self.assertEqual(comment._replies, None)

    def test_spambox_comments_replies_are_none(self):
        predicate = lambda item: isinstance(item, Comment)
        sequence = self.r.get_subreddit(self.sr).get_spam()
        comment = self.first(sequence, predicate)
        self.assertEqual(comment._replies, None)

    def test_user_comment_replies_are_none(self):
        predicate = lambda item: isinstance(item, Comment)
        comment = self.first(self.r.user.get_comments(), predicate)
        self.assertEqual(comment._replies, None)


class FlairTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()
        self.subreddit = self.r.get_subreddit(self.sr)

    def test_add_link_flair(self):
        flair_text = 'Flair: %s' % self.r.modhash
        sub = next(self.subreddit.get_new())
        self.subreddit.set_flair(sub, flair_text)
        sub = self.r.get_submission(sub.permalink)
        self.assertEqual(sub.link_flair_text, flair_text)

    def test_add_link_flair_through_submission(self):
        flair_text = 'Flair: %s' % self.r.modhash
        sub = next(self.subreddit.get_new())
        sub.set_flair(flair_text)
        sub = self.r.get_submission(sub.permalink)
        self.assertEqual(sub.link_flair_text, flair_text)

    def test_add_link_flair_to_invalid_subreddit(self):
        sub = next(self.r.get_subreddit('python').get_new())
        self.assertRaises(HTTPError, self.subreddit.set_flair, sub, 'text')

    def test_add_user_flair_by_subreddit_name(self):
        flair_text = 'Flair: %s' % self.r.modhash
        self.r.set_flair(self.sr, self.r.user, flair_text)
        flair = self.r.get_flair(self.sr, self.r.user)
        self.assertEqual(flair['flair_text'], flair_text)
        self.assertEqual(flair['flair_css_class'], None)

    def test_add_user_flair_to_invalid_user(self):
        self.assertRaises(errors.InvalidFlairTarget, self.subreddit.set_flair,
                          self.invalid_user_name)

    def test_add_user_flair_by_name(self):
        flair_text = 'Flair: {0}'.format(self.r.modhash)
        flair_css = self.r.modhash
        self.subreddit.set_flair(text_type(self.r.user), flair_text, flair_css)
        flair = self.subreddit.get_flair(self.r.user)
        self.assertEqual(flair['flair_text'], flair_text)
        self.assertEqual(flair['flair_css_class'], flair_css)

    def test_clear_user_flair(self):
        self.subreddit.set_flair(self.r.user)
        flair = self.subreddit.get_flair(self.r.user)
        self.assertEqual(flair['flair_text'], None)
        self.assertEqual(flair['flair_css_class'], None)

    def test_delete_flair(self):
        flair = list(self.subreddit.get_flair_list(limit=1))[0]
        self.subreddit.delete_flair(flair['user'])
        self.assertTrue(flair not in self.subreddit.get_flair_list())

    def test_flair_csv_and_flair_list(self):
        # Clear all flair
        self.subreddit.clear_all_flair()
        self.delay(5)  # Wait for flair to clear
        self.assertEqual([], list(self.subreddit.get_flair_list()))

        # Set flair
        flair_mapping = [{'user': 'reddit', 'flair_text': 'dev'},
                         {'user': self.un, 'flair_css_class': 'xx'},
                         {'user': self.other_user_name,
                          'flair_text': 'AWESOME',
                          'flair_css_class': 'css'}]
        self.subreddit.set_flair_csv(flair_mapping)
        self.assertEqual([], flair_diff(flair_mapping,
                                        list(self.subreddit.get_flair_list())))

    def test_flair_csv_many(self):
        users = ('reddit', self.un, self.other_user_name)
        flair_text_a = 'Flair: %s' % self.r.modhash
        flair_text_b = 'Flair: %s' % self.r.modhash
        flair_mapping = [{'user': 'reddit', 'flair_text': flair_text_a}] * 99
        for user in users:
            flair_mapping.append({'user': user, 'flair_text': flair_text_b})
        self.subreddit.set_flair_csv(flair_mapping)
        for user in users:
            flair = self.subreddit.get_flair(user)
            self.assertEqual(flair['flair_text'], flair_text_b)

    def test_flair_csv_optional_args(self):
        flair_mapping = [{'user': 'reddit', 'flair_text': 'reddit'},
                         {'user': self.other_user_name, 'flair_css_class':
                          'blah'}]
        self.subreddit.set_flair_csv(flair_mapping)

    def test_flair_csv_empty(self):
        self.assertRaises(errors.ClientException,
                          self.subreddit.set_flair_csv, [])

    def test_flair_csv_requires_user(self):
        flair_mapping = [{'flair_text': 'hsdf'}]
        self.assertRaises(errors.ClientException,
                          self.subreddit.set_flair_csv, flair_mapping)


class FlairSelectTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()
        self.subreddit = self.r.get_subreddit(self.priv_sr)
        self.user_flair_templates = {
            'UserCssClassOne':  ('21e00aae-09cf-11e3-a4f1-12313d281541',
                                 'default_user_flair_text_one'),
            'UserCssClassTwo':  ('2f6504c2-09cf-11e3-9d8d-12313d281541',
                                 'default_user_flair_text_two')
        }
        self.link_flair_templates = {
            'LinkCssClassOne':  ('36a573c0-09cf-11e3-b5f7-12313d096169',
                                 'default_link_flair_text_one'),
            'LinkCssClassTwo':  ('3b73f516-09cf-11e3-9a71-12313d281541',
                                 'default_link_flair_text_two')
        }

    def get_different_user_flair_class(self):
        flair = self.r.get_flair(self.subreddit, self.r.user)
        if flair == self.user_flair_templates.keys()[0]:
            different_flair = self.user_flair_templates.keys()[1]
        else:
            different_flair = self.user_flair_templates.keys()[0]
        return different_flair

    def get_different_link_flair_class(self, submission):
        flair = submission.link_flair_css_class
        if flair == self.link_flair_templates.keys()[0]:
            different_flair = self.link_flair_templates.keys()[1]
        else:
            different_flair = self.link_flair_templates.keys()[0]
        return different_flair

    def test_select_user_flair(self):
        flair_class = self.get_different_user_flair_class()
        flair_id = self.user_flair_templates[flair_class][0]
        flair_default_text = self.user_flair_templates[flair_class][1]
        self.r.select_flair(item=self.subreddit,
                            flair_template_id=flair_id)
        flair = self.r.get_flair(self.subreddit, self.r.user)
        self.assertEqual(flair['flair_text'], flair_default_text)
        self.assertEqual(flair['flair_css_class'], flair_class)

    def test_select_link_flair(self):
        sub = next(self.subreddit.get_new())
        flair_class = self.get_different_link_flair_class(sub)
        flair_id = self.link_flair_templates[flair_class][0]
        flair_default_text = self.link_flair_templates[flair_class][1]
        self.r.select_flair(item=sub,
                            flair_template_id=flair_id)
        sub = self.r.get_submission(sub.permalink)
        self.assertEqual(sub.link_flair_text, flair_default_text)
        self.assertEqual(sub.link_flair_css_class, flair_class)

    def test_select_user_flair_custom_text(self):
        flair_class = self.get_different_user_flair_class()
        flair_id = self.user_flair_templates[flair_class][0]
        flair_text = 'Flair: %s' % self.r.modhash
        self.r.select_flair(item=self.subreddit,
                            flair_template_id=flair_id,
                            flair_text=flair_text)
        flair = self.r.get_flair(self.subreddit, self.r.user)
        self.assertEqual(flair['flair_text'], flair_text)
        self.assertEqual(flair['flair_css_class'], flair_class)

    def test_select_link_flair_custom_text(self):
        sub = next(self.subreddit.get_new())
        flair_class = self.get_different_link_flair_class(sub)
        flair_id = self.link_flair_templates[flair_class][0]
        flair_text = 'Flair: %s' % self.r.modhash
        self.r.select_flair(item=sub,
                            flair_template_id=flair_id,
                            flair_text=flair_text)
        sub = self.r.get_submission(sub.permalink)
        self.assertEqual(sub.link_flair_text, flair_text)
        self.assertEqual(sub.link_flair_css_class, flair_class)

    def test_select_user_flair_remove(self):
        flair = self.r.get_flair(self.subreddit, self.r.user)
        if flair['flair_css_class'] is None:
            flair_class = self.get_different_user_flair_class()
            flair_id = self.user_flair_templates[flair_class][0]
            self.r.select_flair(item=self.subreddit,
                                flair_template_id=flair_id)
        self.r.select_flair(item=self.subreddit)
        flair = self.r.get_flair(self.subreddit, self.r.user)
        self.assertEqual(flair['flair_text'], None)
        self.assertEqual(flair['flair_css_class'], None)

    def test_select_link_flair_remove(self):
        sub = next(self.subreddit.get_new())
        if sub.link_flair_css_class is None:
            flair_class = self.get_different_link_flair_class(sub)
            flair_id = self.link_flair_templates[flair_class][0]
            self.r.select_flair(item=sub,
                                flair_template_id=flair_id)
        self.r.select_flair(item=sub)
        sub = self.r.get_submission(sub.permalink)
        self.assertEqual(sub.link_flair_text, None)
        self.assertEqual(sub.link_flair_css_class, None)


class FlairTemplateTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()
        self.subreddit = self.r.get_subreddit(self.sr)

    def test_add_user_template(self):
        self.subreddit.add_flair_template('text', 'css', True)

    def test_add_link_template(self):
        self.subreddit.add_flair_template('text', 'css', True, True)
        self.subreddit.add_flair_template(text='text', is_link=True)
        self.subreddit.add_flair_template(css_class='blah', is_link=True)
        self.subreddit.add_flair_template(is_link=True)

    def test_clear_user_templates(self):
        self.subreddit.clear_flair_templates()

    def test_clear_link_templates(self):
        self.subreddit.clear_flair_templates(True)


class ImageTests(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()
        self.subreddit = self.r.get_subreddit(self.sr)
        test_dir = os.path.dirname(sys.modules[__name__].__file__)
        self.image_path = os.path.join(test_dir, 'files', '{0}')

    def test_delete_header(self):
        self.subreddit.delete_image(header=True)

    def test_delete_image(self):
        images = self.subreddit.get_stylesheet()['images']
        for img_data in images[:5]:
            self.subreddit.delete_image(name=img_data['name'])
        updated_images = self.subreddit.get_stylesheet()['images']
        self.assertNotEqual(images, updated_images)

    def test_delete_invalid_image(self):
        self.assertRaises(errors.BadCSSName,
                          self.subreddit.delete_image, 'invalid_image_name')

    def test_delete_invalid_params(self):
        self.assertRaises(TypeError, self.subreddit.delete_image, name='Foo',
                          header=True)

    def test_upload_invalid_file_path(self):
        self.assertRaises(IOError, self.subreddit.upload_image, 'nonexistent')

    def test_upload_uerinvalid_image(self):
        image = self.image_path.format('white-square.tiff')
        self.assertRaises(errors.ClientException, self.subreddit.upload_image,
                          image)

    def test_upload_invalid_image_too_small(self):
        image = self.image_path.format('invalid.jpg')
        self.assertRaises(errors.ClientException, self.subreddit.upload_image,
                          image)

    def test_upload_invalid_image_too_large(self):
        image = self.image_path.format('big')
        self.assertRaises(errors.ClientException, self.subreddit.upload_image,
                          image)

    def test_upload_invalid_params(self):
        image = self.image_path.format('white-square.jpg')
        self.assertRaises(TypeError, self.subreddit.upload_image, image,
                          name='Foo', header=True)

    def test_upload_invalid_image_path(self):
        self.assertRaises(IOError, self.subreddit.upload_image, 'bar.png')

    def test_upload_jpg_header(self):
        image = self.image_path.format('white-square.jpg')
        self.assertTrue(self.subreddit.upload_image(image, header=True))

    def test_upload_jpg_image(self):
        image = self.image_path.format('white-square.jpg')
        self.assertTrue(self.subreddit.upload_image(image))

    def test_upload_jpg_image_named(self):
        image = self.image_path.format('white-square.jpg')
        name = text_type(self.r.modhash)
        self.assertTrue(self.subreddit.upload_image(image, name))
        images_json = self.subreddit.get_stylesheet()['images']
        self.assertTrue(any(name in text_type(x['name']) for x in images_json))

    def test_upload_jpg_image_no_extension(self):
        image = self.image_path.format('white-square')
        self.assertTrue(self.subreddit.upload_image(image))

    def test_upload_png_header(self):
        image = self.image_path.format('white-square.png')
        self.assertTrue(self.subreddit.upload_image(image, header=True))

    def test_upload_png_image(self):
        image = self.image_path.format('white-square.png')
        self.assertTrue(self.subreddit.upload_image(image))

    def test_upload_png_image_named(self):
        image = self.image_path.format('white-square.png')
        name = text_type(self.r.modhash)
        self.assertTrue(self.subreddit.upload_image(image, name))
        images_json = self.subreddit.get_stylesheet()['images']
        self.assertTrue(any(name in text_type(x['name']) for x in images_json))


class ModeratorSubmissionTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()
        self.subreddit = self.r.get_subreddit(self.sr)

    def test_approve(self):
        submission = next(self.subreddit.get_spam())
        if not submission:
            self.fail('Could not find a submission to approve.')
        submission.approve()
        predicate = lambda approved: approved.id == submission.id
        self.first(self.subreddit.get_new(), predicate)

    def test_ignore_reports(self):
        submission = next(self.subreddit.get_new())
        self.assertFalse(submission in self.subreddit.get_mod_log())
        submission.ignore_reports()
        submission.report()
        self.disable_cache()
        submission.refresh()
        self.assertFalse(submission in self.subreddit.get_mod_log())
        self.assertTrue(submission.num_reports > 0)

    def test_remove(self):
        submission = next(self.subreddit.get_new())
        if not submission:
            self.fail('Could not find a submission to remove.')
        submission.remove()
        predicate = lambda removed: removed.id == submission.id
        self.first(self.subreddit.get_spam(), predicate)


class MultiredditTest(unittest.TestCase, AuthenticatedHelper):
    def setUp(self):
        self.configure()

    def test_get_my_multis(self):
        mymultis = self.r.get_my_multis()
        multireddit = mymultis[0]
        self.assertEqual(self.multi_name.lower(),
                         multireddit.display_name.lower())
        self.assertEqual([], multireddit.subreddits)

    def test_get_multireddit_from_user(self):
        multi = self.r.user.get_multireddit(self.multi_name)
        self.assertEqual(self.r.user.name.lower(), multi.author.name.lower())

    def test_get_new(self):
        multi = self.r.user.get_multireddit(self.multi_name)
        new = list(multi.get_new())
        self.assertEqual(0, len(new))