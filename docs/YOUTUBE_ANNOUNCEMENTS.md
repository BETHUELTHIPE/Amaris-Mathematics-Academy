# Publish YouTube announcements

An active Django staff superuser can create, edit, publish, schedule, unpublish
and delete announcements containing a YouTube video or playlist. Ordinary staff,
tutors and students cannot manage announcements, even if model permissions have
been assigned to an ordinary staff account.

1. Sign in to Django Admin and open **Announcements → Add announcement**.
2. Enter the announcement title and message.
3. Under **YouTube**, paste a video or playlist URL. Supported formats include
   watch links, `youtu.be` share links, Shorts, live video links, playlist links,
   and YouTube Studio video-edit/playlist-management links.
4. Save as a draft. The saved record provides **Preview on YouTube**.
5. Select **Is published** to publish now, or set the publication date/time for
   scheduling. An optional expiry automatically removes the notice from the feed.
6. Open the public **Announcements** page. The video/playlist appears alongside
   existing announcement text and uploaded images, MP4/WebM videos or PDFs.

For the supplied Studio URL:

```text
https://studio.youtube.com/playlist/PLU1CWISq1SWo/videos
```

The saved visitor link becomes:

```text
https://www.youtube.com/playlist?list=PLU1CWISq1SWo
```

This validates URL structure and converts the management link. It does not prove
that the playlist exists, is accessible, or permits embedding. Its availability
could not be verified during implementation.

Videos and playlists must be publicly viewable or unlisted, and individual videos
must allow embedding. Private, deleted, region/age-restricted or owner-disabled
videos may not play. The public player includes **Open on YouTube** as a fallback.
The page does not autoplay, uses a lazy privacy-enhanced embed, and keeps the
referrer origin needed by YouTube's player. Captions are controlled by YouTube;
add suitable captions through YouTube Studio.

Publishing on this website does not grant YouTube channel permissions or upload
new files to YouTube. Channel ownership, uploads and YouTube privacy settings
remain managed in YouTube Studio. No YouTube OAuth token or API key is required
for these announcement embeds.

## Release

The backend adds one optional blank field; existing announcements remain valid.
The public API only exposes notices that are published, due and not expired.
Only validated IDs are used to build iframe URLs; other origins, credentials,
executable URLs and malformed IDs are rejected. HTML iframe snippets are not
accepted.

Deploy the reviewed backend migration before the public frontend. The frontend
also works with the preceding API, where the optional YouTube field is absent.
Apply the normal staging and production release checks. Neither a live database
migration nor a public announcement is created by implementing or testing this
feature. Retain the optional column if rolling back application code.
