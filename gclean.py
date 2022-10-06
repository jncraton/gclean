import time
import re
import imaplib
import email
import random
import time
import html2text
from email.utils import parsedate_tz, mktime_tz, formatdate
import signal

import config


def clean_text(text):
    """
    >>> clean_text(' text')
    ' text'
    >>> clean_text(' \t    text')
    ' text'
    >>> clean_text('|')
    ''
    >>> clean_text(' | |')
    ''
    >>> clean_text(' | | text')
    ' | | text'
    >>> clean_text(u' \\u00a0| \\u00a0 |  \\r\\ntest\\r\\n'.encode('utf8')) # Contains non-breaking spaces
    '\\r\\ntest\\r\\n'
    >>> clean_text('-=')
    ''
    >>> clean_text('| \t')
    ''
    >>> clean_text('| \ta\\n  text')
    'a\\n text'
    """
    try:
        text = text.decode("utf8")
    except:
        pass
    text = re.sub("\t", " ", text, flags=re.M)
    text = re.sub("^\|[\| \t]*", "", text, flags=re.M)
    text = re.sub("^[\-\=][\-\=\| \t]*", "", text, flags=re.M)
    text = re.sub("^  +", " ", text, flags=re.M)

    text = re.sub(r"^[\| \t\u00A0\uC2A0]*\r$", "\r", text, flags=re.M | re.UNICODE)
    text = re.sub(r"^[\| \t\u00A0\uC2A0]*$", "", text, flags=re.M | re.UNICODE)

    text = re.sub("^ *$", "", text, flags=re.M)
    text = re.sub("\r\n\r\n[\r\n]*", "\r\n\r\n", text)
    text = re.sub("\r\r[\r]*", "\r\r", text)
    text = re.sub("\n\n[\n]*", "\n\n", text)
    try:
        text = text.encode("utf8")
    except:
        pass

    return text


kill_after = False

if __name__ == "__main__":

    def kb_int(signal, frame):
        global kill_after
        print("Keyboard interupt. Killing after finishing this message...")
        kill_after = True

    signal.signal(signal.SIGINT, kb_int)

    def get_labels(message_id):
        result = mail.uid("fetch", message_id, "X-GM-LABELS")
        print(("Getting current labels...%s" % result[0]))

        labels_string = result[1][0].decode()

        labels_string = re.sub(r"\d+ \(X-GM-LABELS \(", "", labels_string)
        labels_string = re.sub(r"\) UID \d+\)", "", labels_string)

        labels = []
        label = ""
        quoted = False

        for char in labels_string:
            if char == '"':
                quoted = not quoted
            elif char == " " and not quoted:
                labels.append(label.replace("\\\\", "\\"))
                label = ""
            else:
                label = label + char
        if label:
            labels.append(label.replace("\\\\", "\\"))

        print("Current labels " + str(labels))

        return labels

    def cleaned_headers(msg):
        content = msg.as_string()

        content = content.replace("\r\n", "\n")
        content = re.sub(r"(\r|\n)", "\r\n", content)

        match = re.match(r".*?\r\n(\r\n.*)", content, flags=re.MULTILINE | re.DOTALL)

        content = match.group(1)

        headers = ""
        kept = []

        excluded_headers = [
            "thread-topic",
            "in-reply-to",
            "references",
            "thread-index",
            "message-id",
            "content-class",
            "content-language",
            "received",
            "return-path",
            "received-spf",
            "authentication-results",
            "dkim-signature",
            "disposition-notification-to",
            "resent-from",
            "accept-language",
            "domainkey-signature",
            "delivered-to",
            "feedback-id",
            "list-unsubscribe",
            "errors-to",
            "precedence",
            "bounces-to",
            "pp-correlation-id",
            "amq-delivery-message-id",
            "content-disposition",
            "content-id",
            "arc-seal",
            "arc-message-signature",
            "arc-authentication-results",
            "authentication-results-original",
            "spamdiagnosticoutput",
            "spamdiagnosticmetadata",
            "list-help",
            "list-archive",
            "list-post",
            "list-id",
        ]

        # Remove useless headers
        for header in list(msg.keys()):
            if (
                not header.lower().startswith("x-")
                and not header.lower() in excluded_headers
            ):
                kept.append(header)
                headers += header + ": " + msg[header] + "\r\n"
        print(("Kept headers:%s" % ",".join(kept)))

        headers += "message-id: %08x\r\n" % random.randint(
            0, 4294967296
        )  # nonce to create a "different" message

        return headers + content

    mail = imaplib.IMAP4_SSL("imap.gmail.com")

    mail.login(config.email, config.password)

    def search():
        mail.select('"[Google Mail]/All Mail"')
        return mail.uid(
            "search",
            None,
            "X-GM-RAW",
            '"(label:_clean OR label:_zero_att) -label:_cleaned -in:inbox"',
        )

    search_result, message_ids = search()

    while search_result == "OK" and message_ids[0]:
        print(f"{len(message_ids[0].split(b' '))} messages left")

        for message_id in [message_ids[0].decode().split(" ")[0]]:
            has_plain = False

            print("Fetching " + message_id)

            flags = mail.uid("fetch", message_id, "FLAGS")
            print(("Getting current flags...%s" % flags[0]))

            is_read = b"\seen" in flags[1][0].lower()

            typ, msg_data = mail.uid("fetch", message_id, "(RFC822)")

            labels = get_labels(message_id)

            converted_to_plain = False

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    print("Parsing " + message_id)
                    msg = email.message_from_string(response_part[1].decode())

                    text_part = None

                    # Try to grab the longest plain text block
                    for part in msg.walk():
                        if "text/plain" in part.get_content_type():
                            has_plain = True
                            if not text_part or (
                                len(part.get_payload(decode=True))
                                > len(text_part.get_payload(decode=True))
                            ):
                                text_part = part

                    # Try to grab text from the HTML if there isn't a text block, or it's short
                    if not has_plain or (
                        text_part and len(text_part.get_payload(decode=True)) < 20
                    ):
                        for part in msg.walk():
                            if "text/html" in part.get_content_type():
                                h = html2text.HTML2Text()
                                h.ignore_links = True
                                h.ignore_images = True
                                for charset in [part.get_content_charset(), 'utf-8', 'latin1']:
                                    try:
                                        payload = part.get_payload(decode=True).decode(charset)
                                        break
                                    except UnicodeDecodeError:
                                        pass
                                text = h.handle(payload)
                                text_part = email.message.Message()
                                text_part.set_payload(text, part.get_content_charset())

                    if text_part and "_zero_att" in labels:
                        # Switch message to text/plain instead of multipart
                        print("Preparing to write as text/plain message")

                        msg.set_payload(clean_text(text_part.get_payload(decode=True)))
                        for header, value in list(text_part.items()):
                            print(("Merging %s header" % header))
                            del msg[header]
                            msg.add_header(header, value)
                        # Force quoted-printable encoding
                        del msg["Content-Transfer-Encoding"]
                        msg.add_header("Content-Transfer-Encoding", "quoted-printable")
                        converted_to_plain = True
                    else:
                        # Leave as multipart and zero extra sections
                        for part in msg.walk():
                            type = part.get_content_type()
                            if "html" in type and has_plain:
                                print("Removing " + type + " from " + message_id)
                                part.set_payload("")
                                if type == "text/html":
                                    del part["Content-Type"]
                                    part["Content-Type"] = "deleted"
                            elif (
                                "_zero_att" in labels
                                and not "text" in type
                                and not part.is_multipart()
                            ):
                                print(
                                    "Removing attachment "
                                    + type
                                    + " from "
                                    + message_id
                                )
                                part.set_payload("")
                            else:
                                print("Keeping " + type + " from " + message_id)

            print(("Replacing " + message_id + " " + msg["Subject"][:65]))
            date = mktime_tz(parsedate_tz(msg["Date"]))

            result = mail.append(
                '"[Google Mail]/All Mail"', "", date, cleaned_headers(msg).encode()
            )
            print(f"Added new message... {result[0]}")
            if result[0] == "OK":
                print(result)
                match = re.match(r".*APPENDUID \d (\d+)", result[1][0].decode())
                new_id = match.group(1)

                labels.append("_cleaned")

                if converted_to_plain:
                    labels.append("_converted_to_plain")

                if is_read:
                    result = mail.uid("store", new_id, "+FLAGS", "\\Seen")
                    print(f"Marking as read...{result[0]}")

                result = mail.uid("fetch", message_id, "(RFC822)")
                print(f"Fetched original message...{result[0]}")
                if new_id == message_id:
                    print("New message given current UID. Aborting.")
                elif not result[1][0]:
                    print("Appended message replaced current message (no changes?)")
                else:
                    for label in labels:
                        if not label == "_clean" and not label == "_zero_att":
                            if ' ' in label:
                                label = f'"{label}"'
                            result = mail.uid("store", new_id, "+X-GM-LABELS", label)
                            print(f"Added label {label} {result[0]}")

                            assert result[0] == "OK"

                    print(
                        (
                            "Deleting original message..."
                            + str(
                                mail.uid("store", message_id, "+FLAGS", "\\Deleted")[0]
                            )
                        )
                    )
                    print(("Expunging mailbox..." + mail.expunge()[0]))

        if kill_after:
            exit(0)
        search_result, message_ids = search()
