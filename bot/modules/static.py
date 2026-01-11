WelcomeText = \
"""
Hi **%(first_name)s**, send me a file to instantly generate download and stream links.

Send any file directly to me and I'll generate download and stream links for you.

**Available Commands:**
- /start - Show this welcome message
- /setapikey - Link your publisher API key to upload files
- /myaccount - View your linked publisher account details
"""

FileLinksText = \
"""
**Download Link:**
`%(dl_link)s`
"""

MediaLinksText = \
"""
**Download Link:**
`%(dl_link)s`
**Stream Link:**
`%(stream_link)s`
"""

InvalidQueryText = \
"""
Query data mismatched.
"""

MessageNotExist = \
"""
File revoked or not exist.
"""

LinkRevokedText = \
"""
The link has been revoked. It may take some time for the changes to take effect.
"""

InvalidPayloadText = \
"""
Invalid payload.
"""

MediaTypeNotSupportedText = \
"""
Sorry, this media type is not supported.
"""