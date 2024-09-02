"use strict";

const router = require("../router.js");
const api = require("../api.js");
const settings = require("../models/settings.js");
const uri = require("../util/uri.js");
const PostList = require("../models/post_list.js");
const topNavigation = require("../models/top_navigation.js");
const PageController = require("../controllers/page_controller.js");
const PostsHeaderView = require("../views/posts_header_view.js");
const PostsPageView = require("../views/posts_page_view.js");
const EmptyView = require("../views/empty_view.js");

const fields = [
    "id",
    "thumbnailUrl",
    "customThumbnailUrl",
    "type",
    "safety",
    "score",
    "favoriteCount",
    "commentCount",
    // "tags",
    "flags",
    "version",
];

const postUpdateNum = 2;

class PostListController {
    constructor(ctx) {
        this._pageController = new PageController();

        if (!api.hasPrivilege("posts:list")) {
            this._view = new EmptyView();
            this._view.showError("You don't have privileges to view posts.");
            return;
        }

        this._ctx = ctx;

        topNavigation.activate("posts");
        topNavigation.setTitle("Listing posts");

        this._headerView = new PostsHeaderView({
            hostNode: this._pageController.view.pageHeaderHolderNode,
            parameters: ctx.parameters,
            enableSafety: api.safetyEnabled(),
            canViewPostsUnsafe: api.hasPrivilege("posts:view:unsafe"),
            canBulkEditTags: api.hasPrivilege("posts:bulk-edit:tags"),
            canBulkEditSafety: api.hasPrivilege("posts:bulk-edit:safety"),
            canBulkDelete: api.hasPrivilege("posts:bulk-edit:delete"),
            bulkEdit: {
                tags: this._bulkEditTags,
                flag: this._bulkEditFlag,
            },
        });
        this._headerView.addEventListener("navigate", (e) =>
            this._evtNavigate(e)
        );

        if (this._headerView._bulkDeleteEditor) {
            this._headerView._bulkDeleteEditor.addEventListener(
                "deleteSelectedPosts",
                (e) => {
                    this._evtDeleteSelectedPosts(e);
                }
            );
        }

        this._postsMarkedForDeletion = [];
        this._postUpdateQueue = [];
        this._postUpdateActive = [];
        this._syncPageController();
    }

    showSuccess(message) {
        this._pageController.showSuccess(message);
    }

    get _bulkEditTags() {
        return (this._ctx.parameters.tag || "").split(/\s+/).filter((s) => s);
    }

    get _bulkEditFlag() {
        return (this._ctx.parameters.flag || "")
    }

    _evtNavigate(e) {
        router.showNoDispatch(
            uri.formatClientLink("posts", e.detail.parameters)
        );
        Object.assign(this._ctx.parameters, e.detail.parameters);
        this._syncPageController();
    }

    _evtTag(e) {
        Promise.all(
            this._bulkEditTags.map((tag) => e.detail.post.tags.addByName(tag))
        )
            .then(e.detail.post.save())
            .catch((error) => window.alert(error.message));
    }

    _evtUntag(e) {
        for (let tag of this._bulkEditTags) {
            e.detail.post.tags.removeByName(tag);
        }
        e.detail.post.save().catch((error) => window.alert(error.message));
    }

    _queueUpdate(post) {
        if (post) {
            this._postUpdateQueue.push(post);
        }
        if (this._postUpdateActive.length < postUpdateNum) {
            const nextPost = this._postUpdateQueue.shift();
            if (nextPost) {
                this._postUpdateActive.push(nextPost._id);
                nextPost.save().catch((error) => window.alert(error.message)).then(() => {
                    this._postUpdateActive = this._postUpdateActive.filter(id => id != nextPost._id);
                    this._queueUpdate();
                });
                if (this._postUpdateActive.length < postUpdateNum) {
                    this._queueUpdate();
                }
            }
            else {
                console.debug('queue empty');
            }
        }
    }

    _evtFlag(e) {
        if (e.detail.post.flags.indexOf(this._bulkEditFlag) == -1) {
            e.detail.post.flags.push(this._bulkEditFlag);
            // e.detail.post.save().catch((error) => window.alert(error.message));
            this._queueUpdate(e.detail.post);
        }
    }

    _evtUnFlag(e) {
        if (e.detail.post.flags.indexOf(this._bulkEditFlag) > -1) {
            e.detail.post.flags = e.detail.post.flags.filter(f => f != this._bulkEditFlag);
            // e.detail.post.save().catch((error) => window.alert(error.message));
            this._queueUpdate(e.detail.post);
        }
    }

    _evtChangeSafety(e) {
        e.detail.post.safety = e.detail.safety;
        e.detail.post.save().catch((error) => window.alert(error.message));
    }

    _evtMarkForDeletion(e) {
        const postId = e.detail;

        // Add or remove post from delete list
        if (e.detail.delete) {
            this._postsMarkedForDeletion.push(e.detail.post);
        } else {
            this._postsMarkedForDeletion = this._postsMarkedForDeletion.filter(
                (x) => x.id != e.detail.post.id
            );
        }
    }

    _evtDeleteSelectedPosts(e) {
        if (this._postsMarkedForDeletion.length == 0) return;

        if (
            confirm(
                `Are you sure you want to delete ${this._postsMarkedForDeletion.length} posts?`
            )
        ) {
            const prom = async () => {
                const posts = this._postsMarkedForDeletion.map((post) => post);
                for (const post of posts) {
                    await post.delete();
                }
                return Promise.resolve();
            };
            prom()
                .catch((error) => window.alert(error.message))
                .then(() => {
                    this._postsMarkedForDeletion = [];
                    this._headerView._navigate();
                });
        }
    }

    _evtPostEnter(e) {
        const post = e.detail.post;
        if (post.tags.length > 0) {
            return;
        }
        api.get(uri.formatApiLink("post", post.id, { fields: "tagNames" })).then(response => {
            for (const tag of response.tagNames) {
                post.tags.addByName(tag);
            }
            e.detail.element.title += "\n\n" + post.tagNames.join(" ");
        });
    }

    _syncPageController() {
        this._pageController.run({
            parameters: this._ctx.parameters,
            browserState: this._ctx.state,
            defaultLimit: parseInt(settings.get().postsPerPage),
            getClientUrlForPage: (offset, limit) => {
                const parameters = Object.assign({}, this._ctx.parameters, {
                    offset: offset,
                    limit: limit,
                });
                return uri.formatClientLink("posts", parameters);
            },
            requestPage: (offset, limit) => {
                return PostList.search(
                    this._ctx.parameters.query,
                    offset,
                    limit,
                    fields
                );
            },
            pageRenderer: (pageCtx) => {
                Object.assign(pageCtx, {
                    canViewPosts: api.hasPrivilege("posts:view"),
                    canBulkEditTags: api.hasPrivilege("posts:bulk-edit:tags"),
                    canBulkEditSafety: api.hasPrivilege("posts:bulk-edit:safety"),
                    canBulkDelete: api.hasPrivilege("posts:bulk-edit:delete"),
                    bulkEdit: {
                        tags: this._bulkEditTags,
                        flag: this._bulkEditFlag,
                        markedForDeletion: this._postsMarkedForDeletion,
                    },
                    imagesPerRow: parseInt(settings.get().imagesPerRow),
                    imagesPerRowMobile: parseInt(settings.get().imagesPerRowMobile),
                });
                const view = new PostsPageView(pageCtx);
                view.addEventListener("tag", (e) => this._evtTag(e));
                view.addEventListener("untag", (e) => this._evtUntag(e));
                view.addEventListener("flag", (e) => this._evtFlag(e));
                view.addEventListener("unflag", (e) => this._evtUnFlag(e));
                view.addEventListener("changeSafety", (e) =>
                    this._evtChangeSafety(e)
                );
                view.addEventListener("markForDeletion", (e) =>
                    this._evtMarkForDeletion(e)
                );
                view.addEventListener("postEnter", (e) => this._evtPostEnter(e));
                return view;
            },
        });
    }
}

module.exports = (router) => {
    router.enter(["posts"], (ctx, next) => {
        ctx.controller = new PostListController(ctx);
    });
};
