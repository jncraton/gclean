# gclean

Strips the size of Gmail messages by removing attachements and/or converting messages to plain text. Behavior is controlled by assigning labels to messages.

## Usage

1. Create config.py (see config.example.py)
2. Disable IMAP access for every label except "All Mail". Note that this program can't work on messages currently in your inbox, so get to inbox zero before running this. If IMAP access isn't disabled, files emails can't be properly replaced due to them still existing in an accessible folder.
2. Set labels on messages to be cleaned
    - _clean - remove html blocks and eliminate many headers
    - _zero_att - same as _clean but also removes attachements and converts message to text/plain if it was multipart  
3. python gclean.py
