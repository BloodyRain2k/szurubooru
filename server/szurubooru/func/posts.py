import hmac
import logging
from collections import namedtuple
from datetime import datetime
from itertools import tee, chain, islice
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import sqlalchemy as sa

from szurubooru import db, errors, model, rest
from szurubooru.config import config
from szurubooru.func import (
    auth,
    comments,
    files,
    image_hash,
    images,
    mime,
    pools,
    scores,
    serialization,
    tags,
    users,
    util,
)

logger = logging.getLogger(__name__)

_current_directory = ""

def get_directory(check: bool = None, get_min: bool = None):
    if not config["posts"]["use_directories"]:
        return ""
    dir_changed = False
    global _current_directory
    if not _current_directory:
        set_directory(db.session.execute(
            f"SELECT {'min' if get_min else 'max'}(trim(LEADING '0' FROM {model.Post.directory.key})) FROM post"
        ).fetchone()[0])
        dir_changed = True
    if check:
        while 1:
            count = files.scan("posts/" + _current_directory).__len__()
            if count >= config["posts"]["posts_per_directory"]:
                set_directory(get_next_directory())
                dir_changed = True
            else:
                break
    if dir_changed:
        logger.info(f'> new post directory: "{_current_directory}"')
    return _current_directory

def get_next_directory():
    dir_num = int(get_directory())
    return str(dir_num + 1)

def set_directory(new_dir: Union[str,int]):
    global _current_directory
    new_dir = str(new_dir or 0)
    padding = config["posts"]["directory_padding"]
    if padding > 0:
        while new_dir.__len__() < padding:
            new_dir = f"0{new_dir}"
    _current_directory = new_dir
    return new_dir


EMPTY_PIXEL = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00"
    b"\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x01\x00\x2c\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02\x4c\x01\x00\x3b"
)


class PostNotFoundError(errors.NotFoundError):
    pass


class PostAlreadyFeaturedError(errors.ValidationError):
    pass


class PostAlreadyUploadedError(errors.ValidationError):
    def __init__(self, other_post: model.Post) -> None:
        super().__init__(
            "Post already uploaded (%d)" % other_post.post_id,
            {
                "otherPostUrl": get_post_content_url(other_post),
                "otherPostId": other_post.post_id,
            },
        )


class InvalidPostIdError(errors.ValidationError):
    pass


class InvalidPostSafetyError(errors.ValidationError):
    pass


class InvalidPostSourceError(errors.ValidationError):
    pass


class InvalidPostContentError(errors.ValidationError):
    pass


class InvalidPostRelationError(errors.ValidationError):
    pass


class InvalidPostNoteError(errors.ValidationError):
    pass


class InvalidPostFlagError(errors.ValidationError):
    pass


class InvalidPostDescriptionError(errors.ValidationError):
    pass


class InvalidPostTitleError(errors.ValidationError):
    pass


class InvalidPostAltTextError(errors.ValidationError):
    pass


SAFETY_MAP = {
    model.Post.SAFETY_SAFE: "safe",
    model.Post.SAFETY_SKETCHY: "sketchy",
    model.Post.SAFETY_UNSAFE: "unsafe",
}

TYPE_MAP = {
    model.Post.TYPE_IMAGE: "image",
    model.Post.TYPE_ANIMATION: "animation",
    model.Post.TYPE_VIDEO: "video",
    model.Post.TYPE_FLASH: "flash",
}

FLAG_MAP = {
    model.Post.FLAG_LOOP: "loop",
    model.Post.FLAG_SOUND: "sound",
    model.Post.FLAG_TAGME: "tagme",
}

# https://stackoverflow.com/a/1012089
def _get_nearby_iter(post_list):
    previous_item, current_item, next_item = tee(post_list, 3)
    previous_item = chain([None], previous_item)
    next_item = chain(islice(next_item, 1, None), [None])
    return zip(previous_item, current_item, next_item)


def get_post_filename(post: model.Post, without_suffix: bool = None, thumbnail: bool = None) -> str:
    assert post
    p_dir = post.directory + "/" if post.directory else ""
    return "%s%s%d_%s%s" % (
        p_dir,
        (config["thumbnails"]["post_filename_prefix"] if thumbnail else ""),
        post.post_id,
        post.image_key,
        (config["thumbnails"]["post_filename_suffix"] if thumbnail else ""),
    ) + (
        "" if without_suffix or thumbnail \
        else ".%s" % (
            mime.get_extension(post.mime_type) or "dat",
        )
    )


def get_post_content_path(post: model.Post) -> str:
    assert post
    assert post.post_id
    return "posts/%s" % (
        get_post_filename(post),
    )


def get_post_content_url(post: model.Post) -> str:
    assert post
    return "%s/%s" % (
        config["data_url"].rstrip("/"),
        get_post_content_path(post),
    )


def get_post_thumbnail_path(post: model.Post) -> str:
    assert post
    return "generated-thumbnails/%s.jpg" % (
        get_post_filename(post, thumbnail=True),
    )


def get_post_thumbnail_url(post: model.Post) -> str:
    assert post
    return "%s/%s" % (
        config["data_url"].rstrip("/"),
        get_post_thumbnail_path(post),
    )


def get_post_custom_thumbnail_path(post: model.Post) -> str:
    assert post
    return "generated-thumbnails/custom-thumbnails/%s.jpg" % (
        get_post_filename(post, thumbnail=True),
    )


def get_post_custom_thumbnail_url(post: model.Post) -> str:
    assert post
    return "%s/%s" % (
        config["data_url"].rstrip("/"),
        get_post_custom_thumbnail_path(post),
    )


def get_post_custom_content_path(post: model.Post) -> str:
    assert post
    assert post.post_id
    return "posts/custom-thumbnails/%s.dat" % (
        get_post_filename(post),
    )


def serialize_note(note: model.PostNote) -> rest.Response:
    assert note
    return {
        "polygon": note.polygon,
        "text": note.text,
    }


class PostSerializer(serialization.BaseSerializer):
    def __init__(self, post: model.Post, auth_user: model.User) -> None:
        self.post = post
        self.auth_user = auth_user

    def serialize(self, options: List[str]) -> Any:
        serial = super().serialize(options)
        if serial["safety"] == SAFETY_MAP[model.Post.SAFETY_UNSAFE] and not auth.has_privilege(self.auth_user, "posts:view:unsafe"):
            return
        return serial

    def _serializers(self) -> Dict[str, Callable[[], Any]]:
        return {
            "id": self.serialize_id,
            "version": self.serialize_version,
            "creationTime": self.serialize_creation_time,
            "lastEditTime": self.serialize_last_edit_time,
            "safety": self.serialize_safety,
            "source": self.serialize_source,
            "type": self.serialize_type,
            "mimeType": self.serialize_mime,
            "checksum": self.serialize_checksum,
            "checksumMD5": self.serialize_checksum_md5,
            "fileSize": self.serialize_file_size,
            "canvasWidth": self.serialize_canvas_width,
            "canvasHeight": self.serialize_canvas_height,
            "contentUrl": self.serialize_content_url,
            "thumbnailUrl": self.serialize_thumbnail_url,
            "customThumbnailUrl": self.serialize_custom_thumbnail_url,
            "flags": self.serialize_flags,
            "tags": self.serialize_tags,
            "description": self.serialize_description,
            "title": self.serialize_title,
            "altText": self.serialize_alt_text,
            "relations": self.serialize_relations,
            "user": self.serialize_user,
            "score": self.serialize_score,
            "ownScore": self.serialize_own_score,
            "ownFavorite": self.serialize_own_favorite,
            "tagCount": self.serialize_tag_count,
            "favoriteCount": self.serialize_favorite_count,
            "commentCount": self.serialize_comment_count,
            "noteCount": self.serialize_note_count,
            "relationCount": self.serialize_relation_count,
            "featureCount": self.serialize_feature_count,
            "lastFeatureTime": self.serialize_last_feature_time,
            "favoritedBy": self.serialize_favorited_by,
            "notes": self.serialize_notes,
            "comments": self.serialize_comments,
            "pools": self.serialize_pools,
            "directory": self.serialize_directory,
        }

    def serialize_id(self) -> Any:
        return self.post.post_id

    def serialize_version(self) -> Any:
        return self.post.version

    def serialize_creation_time(self) -> Any:
        return self.post.creation_time

    def serialize_last_edit_time(self) -> Any:
        return self.post.last_edit_time

    def serialize_safety(self) -> Any:
        return SAFETY_MAP[self.post.safety]

    def serialize_source(self) -> Any:
        return self.post.source

    def serialize_type(self) -> Any:
        return TYPE_MAP[self.post.type]

    def serialize_mime(self) -> Any:
        return self.post.mime_type

    def serialize_checksum(self) -> Any:
        return self.post.checksum

    def serialize_checksum_md5(self) -> Any:
        return self.post.checksum_md5

    def serialize_file_size(self) -> Any:
        return self.post.file_size

    def serialize_canvas_width(self) -> Any:
        return self.post.canvas_width

    def serialize_canvas_height(self) -> Any:
        return self.post.canvas_height

    def serialize_content_url(self) -> Any:
        return get_post_content_url(self.post)

    def serialize_thumbnail_url(self) -> Any:
        return get_post_thumbnail_url(self.post)

    def serialize_flags(self) -> Any:
        return self.post.flags

    def serialize_tags(self) -> Any:
        return [
            {
                "names": [name.name for name in tag.names],
                "category": tag.category.name,
                "usages": tag.post_count,
            }
            for tag in tags.sort_tags(self.post.tags)
        ]

    def serialize_description(self) -> Any:
        return self.post.description

    def serialize_title(self) -> Any:
        return self.post.title

    def serialize_alt_text(self) -> Any:
        return self.post.alt_text

    def serialize_relations(self) -> Any:
        return sorted(
            {
                post["id"]: post
                for post in [
                    serialize_micro_post(try_get_post_by_id(rel.child_id), self.auth_user)
                    for rel in get_post_relations(self.post.post_id)
                ] if post
            }.values(),
            key=lambda post: post["id"],
        )

    def serialize_user(self) -> Any:
        return users.serialize_micro_user(self.post.user, self.auth_user)

    def serialize_score(self) -> Any:
        return self.post.score

    def serialize_own_score(self) -> Any:
        return scores.get_score(self.post, self.auth_user)

    def serialize_own_favorite(self) -> Any:
        return (
            len(
                [
                    user
                    for user in self.post.favorited_by
                    if user.user_id == self.auth_user.user_id
                ]
            )
            > 0
        )

    def serialize_tag_count(self) -> Any:
        return self.post.tag_count

    def serialize_favorite_count(self) -> Any:
        return self.post.favorite_count

    def serialize_comment_count(self) -> Any:
        return 0

    def serialize_note_count(self) -> Any:
        return self.post.note_count

    def serialize_relation_count(self) -> Any:
        return self.post.relation_count

    def serialize_feature_count(self) -> Any:
        return 0

    def serialize_last_feature_time(self) -> Any:
        return None

    def serialize_favorited_by(self) -> Any:
        return [
            users.serialize_micro_user(rel.user, self.auth_user)
            for rel in self.post.favorited_by
        ]

    def serialize_custom_thumbnail_url(self) -> Any:
        if files.has(get_post_custom_thumbnail_path(self.post)):
            return get_post_custom_thumbnail_url(self.post)

    def serialize_notes(self) -> Any:
        return sorted(
            [serialize_note(note) for note in self.post.notes],
            key=lambda x: x["polygon"],
        )

    def serialize_comments(self) -> Any:
        return []

    def serialize_pools(self) -> List[Any]:
        return [
            pools.serialize_micro_pool(pool)
            for pool in sorted(
                self.post.pools, key=lambda pool: pool.creation_time
            )
        ]

    def serialize_directory(self) -> Any:
        return self.post.directory


def serialize_post(
    post: Optional[model.Post], auth_user: model.User, options: List[str] = []
) -> Optional[rest.Response]:
    if not post:
        return None
    return PostSerializer(post, auth_user).serialize(options)


def serialize_micro_post(
    post: model.Post, auth_user: model.User
) -> Optional[rest.Response]:
    return serialize_post(
        post, auth_user=auth_user, options=["id", "thumbnailUrl", "customThumbnailUrl"]
    )


def get_post_count() -> int:
    return db.session.query(sa.func.count(model.Post.post_id)).one()[0]


def get_post_relations(post_id: int) -> List[model.Post]:
    return db.session.query(model.PostRelation).filter(model.PostRelation.parent_id == post_id).all()


def try_get_post_by_id(post_id: int) -> Optional[model.Post]:
    return (
        db.session.query(model.Post)
        .filter(model.Post.post_id == post_id)
        .one_or_none()
    )


def get_post_by_id(post_id: int) -> model.Post:
    post = try_get_post_by_id(post_id)
    if not post:
        raise PostNotFoundError("Post %r not found." % post_id)
    return post


def get_posts_by_ids(ids: List[int]) -> List[model.Post]:
    if len(ids) == 0:
        return []
    posts = (
        db.session.query(model.Post)
        .filter(sa.sql.or_(model.Post.post_id == post_id for post_id in ids))
        .all()
    )
    id_order = {v: k for k, v in enumerate(ids)}
    return sorted(posts, key=lambda post: id_order.get(post.post_id))


def try_get_current_post_feature() -> Optional[model.PostFeature]:
    return (
        db.session.query(model.PostFeature)
        .order_by(model.PostFeature.time.desc())
        .first()
    )


def try_get_featured_post() -> Optional[model.Post]:
    post_feature = try_get_current_post_feature()
    return post_feature.post if post_feature else None


def create_post(
    content: bytes, tag_names: List[str], user: Optional[model.User]
) -> Tuple[model.Post, List[model.Tag]]:
    post = model.Post()
    post.safety = model.Post.SAFETY_SAFE
    post.user = user
    post.creation_time = datetime.utcnow()
    post.flags = []

    post.type = ""
    post.checksum = ""
    post.mime_type = ""
    post.image_key = ""
    post.directory = get_directory(True)

    update_post_content(post, content)
    new_tags = update_post_tags(post, tag_names)

    db.session.add(post)
    return post, new_tags


def update_post_safety(post: model.Post, safety: str) -> None:
    assert post
    safety = util.flip(SAFETY_MAP).get(safety, None)
    if not safety:
        raise InvalidPostSafetyError(
            "Safety can be either of %r." % list(SAFETY_MAP.values())
        )
    post.safety = safety


def update_post_source(post: model.Post, source: Optional[str]) -> None:
    assert post
    if util.value_exceeds_column_size(source, model.Post.source):
        raise InvalidPostSourceError("Source is too long.")
    post.source = source or None


@sa.events.event.listens_for(model.Post, "after_insert")
def _after_post_insert(
    _mapper: Any, _connection: Any, post: model.Post
) -> None:
    _sync_post_content(post)


@sa.events.event.listens_for(model.Post, "after_update")
def _after_post_update(
    _mapper: Any, _connection: Any, post: model.Post
) -> None:
    _sync_post_content(post)


@sa.events.event.listens_for(model.Post, "before_delete")
def _before_post_delete(
    _mapper: Any, _connection: Any, post: model.Post
) -> None:
    if post.post_id:
        if config["delete_source_files"]:
            pattern = "**/" + config["thumbnails"]["post_filename_prefix"] + post.post_id + "_*"
            for file in files.find("posts", pattern, recursive=True) + files.find("generated-thumbnails", pattern, recursive=True):
                files.delete(file)


def _sync_post_content(post: model.Post) -> None:
    if hasattr(post, "__content"):
        content = getattr(post, "__content")
        files.save(get_post_content_path(post), content)
        generate_post_thumbnail(get_post_thumbnail_path(post), content, seek=False)
        if mime.is_video(post.mime_type):
            generate_post_thumbnail(get_post_custom_thumbnail_path(post), content, seek=True)
        delattr(post, "__content")

    if hasattr(post, "__thumbnail"):
        if getattr(post, "__thumbnail"):
            thumbnail = getattr(post, "__thumbnail")
            files.save(get_post_custom_content_path(post), thumbnail)
            generate_post_thumbnail(get_post_custom_thumbnail_path(post), thumbnail, seek=True)
        else:
            files.delete(get_post_custom_thumbnail_path(post))
        delattr(post, "__thumbnail")


def generate_alternate_formats(
    post: model.Post, content: bytes
) -> List[Tuple[model.Post, List[model.Tag]]]:
    assert post
    assert content
    new_posts = []
    if mime.is_animated_gif(content):
        tag_names = [tag.first_name for tag in post.tags]

        if config["convert"]["gif"]["to_mp4"]:
            mp4_post, new_tags = create_post(
                images.Image(content).to_mp4(), tag_names, post.user
            )
            update_post_flags(mp4_post, ["loop"])
            update_post_safety(mp4_post, post.safety)
            update_post_source(mp4_post, post.source)
            new_posts += [(mp4_post, new_tags)]

        if config["convert"]["gif"]["to_webm"]:
            webm_post, new_tags = create_post(
                images.Image(content).to_webm(), tag_names, post.user
            )
            update_post_flags(webm_post, ["loop"])
            update_post_safety(webm_post, post.safety)
            update_post_source(webm_post, post.source)
            new_posts += [(webm_post, new_tags)]

        db.session.flush()

        new_posts = [p for p in new_posts if p[0] is not None]

        new_relations = [p[0].post_id for p in new_posts]
        if len(new_relations) > 0:
            update_post_relations(post, new_relations)

    return new_posts


def get_default_flags(content: bytes) -> List[str]:
    assert content
    ret = []
    if mime.is_animated_gif(content):
        if images.check_for_loop(content):
            ret.append(model.Post.FLAG_LOOP)
    elif mime.is_video(mime.get_mime_type(content)):
        if images.Image(content).check_for_sound():
            ret.append(model.Post.FLAG_SOUND)
    ret.append(model.Post.FLAG_TAGME)
    return ret


def purge_post_signature(post: model.Post) -> None:
    (
        db.session.query(model.PostSignature)
        .filter(model.PostSignature.post_id == post.post_id)
        .delete()
    )


def generate_post_signature(post: model.Post, content: bytes) -> None:
    try:
        unpacked_signature = image_hash.generate_signature(content)
        packed_signature = image_hash.pack_signature(unpacked_signature)
        words = image_hash.generate_words(unpacked_signature)

        db.session.add(
            model.PostSignature(
                post=post, signature=packed_signature, words=words
            )
        )
    except errors.ProcessingError:
        if not config["allow_broken_uploads"]:
            raise InvalidPostContentError(
                "Unable to generate image hash data."
            )


def update_all_post_signatures() -> None:
    posts_to_hash = (
        db.session.query(model.Post)
        .filter(
            (model.Post.type == model.Post.TYPE_IMAGE)
            | (model.Post.type == model.Post.TYPE_ANIMATION)
        )
        .filter(model.Post.signature == None)  # noqa: E711
        .order_by(model.Post.post_id.asc())
        .all()
    )
    for post in posts_to_hash:
        try:
            generate_post_signature(
                post, files.get(get_post_content_path(post))
            )
            db.session.commit()
            logger.info("Created Signature - Post %d", post.post_id)
        except Exception as ex:
            logger.exception(ex)


def update_all_md5_checksums() -> None:
    posts_to_hash = (
        db.session.query(model.Post)
        .filter(model.Post.checksum_md5 == None)  # noqa: E711
        .order_by(model.Post.post_id.asc())
        .all()
    )
    for post in posts_to_hash:
        try:
            post.checksum_md5 = util.get_md5(
                files.get(get_post_content_path(post))
            )
            db.session.commit()
            logger.info("Created MD5 - Post %d", post.post_id)
        except Exception as ex:
            logger.exception(ex)


def update_post_content(post: model.Post, content: Optional[bytes]) -> None:
    assert post
    if not content:
        raise InvalidPostContentError("Post content missing.")

    update_signature = False
    post.mime_type = mime.get_mime_type(content)
    if mime.is_flash(post.mime_type):
        post.type = model.Post.TYPE_FLASH
    elif mime.is_image(post.mime_type):
        update_signature = True
        if mime.is_animated_gif(content):
            post.type = model.Post.TYPE_ANIMATION
        else:
            post.type = model.Post.TYPE_IMAGE
    elif mime.is_video(post.mime_type):
        post.type = model.Post.TYPE_VIDEO
    else:
        raise InvalidPostContentError(
            "Unhandled file type: %r" % post.mime_type
        )

    post.checksum = util.get_sha1(content)
    post.checksum_md5 = util.get_md5(content)
    # post.image_key = auth.create_password()
    post.image_key = post.image_key if post.image_key else post.checksum_md5
    other_post = (
        db.session.query(model.Post)
        .filter(model.Post.checksum == post.checksum)
        .filter(model.Post.post_id != post.post_id)
        .one_or_none()
    )
    if (
        other_post
        and other_post.post_id
        and other_post.post_id != post.post_id
    ):
        raise PostAlreadyUploadedError(other_post)

    if update_signature:
        purge_post_signature(post)
        post.signature = generate_post_signature(post, content)

    post.file_size = len(content)
    try:
        image = images.Image(content)
        post.canvas_width = image.width
        post.canvas_height = image.height
    except errors.ProcessingError as ex:
        logger.exception(ex)
        if not config["allow_broken_uploads"]:
            raise InvalidPostContentError("Unable to process image metadata")
        else:
            post.canvas_width = None
            post.canvas_height = None
    if (post.canvas_width is not None and post.canvas_width <= 0) or (
        post.canvas_height is not None and post.canvas_height <= 0
    ):
        if not config["allow_broken_uploads"]:
            raise InvalidPostContentError(
                "Invalid image dimensions returned during processing"
            )
        else:
            post.canvas_width = None
            post.canvas_height = None
    setattr(post, "__content", content)


def update_post_thumbnail(
    post: model.Post, content: Optional[bytes] = None
) -> None:
    assert post
    setattr(post, "__thumbnail", content)


def generate_post_thumbnail(path: str, content: bytes, seek=True) -> None:
    try:
        assert content
        image = images.Image(content)
        image.resize_fill(
            int(config["thumbnails"]["post_width"]),
            int(config["thumbnails"]["post_height"]),
            keep_transparency=False,
            seek=seek,
        )
        files.save(path, image.to_jpeg())
    except errors.ProcessingError:
        files.save(path, EMPTY_PIXEL)


def update_post_tags(
    post: model.Post, tag_names: List[str]
) -> List[model.Tag]:
    assert post
    existing_tags, new_tags = tags.get_or_create_tags_by_names(tag_names)
    post.tags = existing_tags + new_tags
    return new_tags


def update_post_relations(post: model.Post, new_post_ids: List[int]) -> None:
    assert post
    try:
        new_post_ids = [int(id) for id in new_post_ids]
    except ValueError:
        raise InvalidPostRelationError("A relation must be numeric post ID.")
    old_posts = get_post_relations(post.post_id)
    old_post_ids = [int(p.child_id) for p in old_posts]
    if new_post_ids:
        new_posts = (
            db.session.query(model.Post)
            .filter(model.Post.post_id.in_(new_post_ids))
            .all()
        )
    else:
        new_posts = []
    if len(new_posts) != len(new_post_ids):
        raise InvalidPostRelationError("One of relations does not exist.")
    if post.post_id in new_post_ids:
        raise InvalidPostRelationError("Post cannot relate to itself.")

    relations_to_del = [p for p in old_posts if p.child_id not in new_post_ids]
    relations_to_add = [p for p in new_posts if p.post_id not in old_post_ids]
    for relation in relations_to_del:
        post.relations.remove(relation)
        relation.relations.remove(post)
    for relation in relations_to_add:
        post.relations.append(relation)
        relation.relations.append(post)


def update_post_notes(post: model.Post, notes: Any) -> None:
    assert post
    post.notes = []
    for note in notes:
        for field in ("polygon", "text"):
            if field not in note:
                raise InvalidPostNoteError("Note is missing %r field." % field)
        if not note["text"]:
            raise InvalidPostNoteError("A note's text cannot be empty.")
        if not isinstance(note["polygon"], (list, tuple)):
            raise InvalidPostNoteError(
                "A note's polygon must be a list of points."
            )
        if len(note["polygon"]) < 3:
            raise InvalidPostNoteError(
                "A note's polygon must have at least 3 points."
            )
        for point in note["polygon"]:
            if not isinstance(point, (list, tuple)):
                raise InvalidPostNoteError(
                    "A note's polygon point must be a list of length 2."
                )
            if len(point) != 2:
                raise InvalidPostNoteError(
                    "A point in note's polygon must have two coordinates."
                )
            try:
                pos_x = float(point[0])
                pos_y = float(point[1])
                if not 0 <= pos_x <= 1 or not 0 <= pos_y <= 1:
                    raise InvalidPostNoteError(
                        "All points must fit in the image (0..1 range)."
                    )
            except ValueError:
                raise InvalidPostNoteError(
                    "A point in note's polygon must be numeric."
                )
        if util.value_exceeds_column_size(note["text"], model.PostNote.text):
            raise InvalidPostNoteError("Note text is too long.")
        post.notes.append(
            model.PostNote(polygon=note["polygon"], text=str(note["text"]))
        )


def update_post_flags(post: model.Post, flags: List[str], remove: bool = False) -> None:
    assert post
    target_flags = []
    for flag in flags:
        if remove and flag == model.Post.FLAG_TAGME:
            continue
        flag = util.flip(FLAG_MAP).get(flag, None)
        if not flag:
            raise InvalidPostFlagError(
                "Flag must be one of %r." % list(FLAG_MAP.values())
            )
        target_flags.append(flag)
    post.flags = target_flags


def update_post_description(post: model.Post, description: str) -> None:
    assert post
    if util.value_exceeds_column_size(description, model.Post.description):
        raise InvalidPostDescriptionError("Description is too long.")
    post.description = description or None


def update_post_title(post: model.Post, title: str) -> None:
    assert post
    if util.value_exceeds_column_size(title, model.Post.title):
        raise InvalidPostTitleError("Title is too long.")
    post.title = title or None


def update_post_alt_text(post: model.Post, alt_text: str) -> None:
    assert post
    if util.value_exceeds_column_size(alt_text, model.Post.alt_text):
        raise InvalidPostAltTextError("Alt text is too long.")
    post.alt_text = alt_text or None


def feature_post(post: model.Post, user: Optional[model.User]) -> None:
    assert post
    post_feature = model.PostFeature()
    post_feature.time = datetime.utcnow()
    post_feature.post = post
    post_feature.user = user
    db.session.add(post_feature)


def delete(post: model.Post) -> None:
    assert post
    db.session.delete(post)


def merge_posts(
    source_post: model.Post, target_post: model.Post, replace_content: bool
) -> None:
    assert source_post
    assert target_post
    if source_post.post_id == target_post.post_id:
        raise InvalidPostRelationError("Cannot merge post with itself.")

    def merge_tables(
        table: model.Base,
        anti_dup_func: Optional[Callable[[model.Base, model.Base], bool]],
        source_post_id: int,
        target_post_id: int,
    ) -> None:
        alias1 = table
        alias2 = sa.orm.util.aliased(table)
        update_stmt = sa.sql.expression.update(alias1).where(
            alias1.post_id == source_post_id
        )

        if anti_dup_func is not None:
            update_stmt = update_stmt.where(
                ~sa.exists()
                .where(anti_dup_func(alias1, alias2))
                .where(alias2.post_id == target_post_id)
            )

        update_stmt = update_stmt.values(post_id=target_post_id)
        db.session.execute(update_stmt)

    def merge_tags(source_post_id: int, target_post_id: int) -> None:
        merge_tables(
            model.PostTag,
            lambda alias1, alias2: alias1.tag_id == alias2.tag_id,
            source_post_id,
            target_post_id,
        )

    def merge_scores(source_post_id: int, target_post_id: int) -> None:
        merge_tables(
            model.PostScore,
            lambda alias1, alias2: alias1.user_id == alias2.user_id,
            source_post_id,
            target_post_id,
        )

    def merge_favorites(source_post_id: int, target_post_id: int) -> None:
        merge_tables(
            model.PostFavorite,
            lambda alias1, alias2: alias1.user_id == alias2.user_id,
            source_post_id,
            target_post_id,
        )

    def merge_comments(source_post_id: int, target_post_id: int) -> None:
        merge_tables(model.Comment, None, source_post_id, target_post_id)

    def merge_relations(source_post_id: int, target_post_id: int) -> None:
        alias1 = model.PostRelation
        alias2 = sa.orm.util.aliased(model.PostRelation)
        update_stmt = (
            sa.sql.expression.update(alias1)
            .where(alias1.parent_id == source_post_id)
            .where(alias1.child_id != target_post_id)
            .where(
                ~sa.exists()
                .where(alias2.child_id == alias1.child_id)
                .where(alias2.parent_id == target_post_id)
            )
            .values(parent_id=target_post_id)
        )
        db.session.execute(update_stmt)

        update_stmt = (
            sa.sql.expression.update(alias1)
            .where(alias1.child_id == source_post_id)
            .where(alias1.parent_id != target_post_id)
            .where(
                ~sa.exists()
                .where(alias2.parent_id == alias1.parent_id)
                .where(alias2.child_id == target_post_id)
            )
            .values(child_id=target_post_id)
        )
        db.session.execute(update_stmt)

    merge_tags(source_post.post_id, target_post.post_id)
    merge_comments(source_post.post_id, target_post.post_id)
    merge_scores(source_post.post_id, target_post.post_id)
    merge_favorites(source_post.post_id, target_post.post_id)
    merge_relations(source_post.post_id, target_post.post_id)

    def transfer_flags(source_post_id: int, target_post_id: int) -> None:
        target = get_post_by_id(target_post_id)
        source = get_post_by_id(source_post_id)
        target.flags = source.flags
        db.session.flush()

    content = None
    if replace_content:
        content = files.get(get_post_content_path(source_post))
        transfer_flags(source_post.post_id, target_post.post_id)

    # fixes unknown issue with SA's cascade deletions
    purge_post_signature(source_post)
    delete(source_post)
    db.session.flush()

    if content is not None:
        update_post_content(target_post, content)


def search_by_image_exact(image_content: bytes) -> Optional[model.Post]:
    checksum = util.get_sha1(image_content)
    return (
        db.session.query(model.Post)
        .filter(model.Post.checksum == checksum)
        .one_or_none()
    )


def search_by_image(image_content: bytes) -> List[Tuple[float, model.Post]]:
    query_signature = image_hash.generate_signature(image_content)
    query_words = image_hash.generate_words(query_signature)

    """
    The unnest function is used here to expand one row containing the 'words'
    array into multiple rows each containing a singular word.

    Documentation of the unnest function can be found here:
    https://www.postgresql.org/docs/9.2/functions-array.html
    """

    dbquery = """
    SELECT s.post_id, s.signature, count(a.query) AS score
    FROM post_signature AS s, unnest(s.words, :q) AS a(word, query)
    WHERE a.word = a.query
    GROUP BY s.post_id
    ORDER BY score DESC LIMIT 100;
    """

    candidates = db.session.execute(dbquery, {"q": query_words})
    data = tuple(
        zip(
            *[
                (post_id, image_hash.unpack_signature(packedsig))
                for post_id, packedsig, score in candidates
            ]
        )
    )
    if data:
        candidate_post_ids, sigarray = data
        distances = image_hash.normalized_distance(sigarray, query_signature)
        return [
            (distance, try_get_post_by_id(candidate_post_id))
            for candidate_post_id, distance in zip(
                candidate_post_ids, distances
            )
            if distance < image_hash.DISTANCE_CUTOFF
        ]
    else:
        return []


PoolPostsNearby = namedtuple('PoolPostsNearby', 'pool first_post prev_post next_post last_post')
def get_pools_nearby(
    post: model.Post
) -> List[PoolPostsNearby]:
    response = []
    pools = post.pools

    for pool in pools:
        prev_post_id = None
        next_post_id = None
        first_post_id = pool.posts[0].post_id,
        last_post_id = pool.posts[-1].post_id,

        for previous_item, current_item, next_item in _get_nearby_iter(pool.posts):
            if post.post_id == current_item.post_id:
                if previous_item != None:
                    prev_post_id = previous_item.post_id
                if next_item != None:
                    next_post_id = next_item.post_id
                break

        resp_entry = PoolPostsNearby(
            pool=pool,
            first_post=first_post_id,
            last_post=last_post_id,
            prev_post=prev_post_id,
            next_post=next_post_id,
        )
        response.append(resp_entry)
    return response


def serialize_safe_post(
    post: Optional[model.Post]
) -> rest.Response:
    return {"id": getattr(post, "post_id", None)} if post else None


def serialize_id_post(
    post_id: Optional[int]
) -> rest.Response:
    return serialize_safe_post(try_get_post_by_id(post_id)) if post_id else None


def serialize_pool_posts_nearby(
    nearby: List[PoolPostsNearby]
) -> Optional[rest.Response]:
    return [
        {
            "pool": pools.serialize_micro_pool(entry.pool),
            "firstPost": serialize_id_post(entry.first_post),
            "lastPost": serialize_id_post(entry.last_post),
            "previousPost": serialize_id_post(entry.prev_post),
            "nextPost": serialize_id_post(entry.next_post),
        } for entry in nearby
    ]
