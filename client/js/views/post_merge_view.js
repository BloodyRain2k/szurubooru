"use strict";

const events = require("../events.js");
const views = require("../util/views.js");

const KEY_RETURN = 13;
const template = views.getTemplate("post-merge");
const sideTemplate = views.getTemplate("post-merge-side");

class PostMergeView extends events.EventTarget {
    constructor(ctx) {
        super();

        this._ctx = ctx;
        this._post = ctx.post;
        this._hostNode = ctx.hostNode;

        this._leftPost = ctx.post;
        this._rightPost = null;
        views.replaceContent(this._hostNode, template(this._ctx));
        views.decorateValidator(this._formNode);

        this._refreshLeftSide();
        this._refreshRightSide();

        this._formNode.addEventListener("submit", (e) => this._evtSubmit(e));
    }

    clearMessages() {
        views.clearMessages(this._hostNode);
    }

    enableForm() {
        views.enableForm(this._formNode);
    }

    disableForm() {
        views.disableForm(this._formNode);
    }

    showSuccess(message) {
        views.showSuccess(this._hostNode, message);
    }

    showError(message) {
        views.showError(this._hostNode, message);
    }

    selectPost(post) {
        this._rightPost = post;
        this._refreshRightSide();
    }

    _refreshLeftSide() {
        this._refreshSide(this._leftPost, this._leftSideNode, "left", false);
        for (let rel of this._hostNode.querySelectorAll("span.relation")) {
            rel.onclick = (evt) => this._setPostField(evt.target.textContent);
        }
    }

    _refreshRightSide() {
        this._refreshSide(this._rightPost, this._rightSideNode, "right", true);
    }

    _refreshSide(post, sideNode, sideName, isEditable) {
        views.replaceContent(
            sideNode,
            sideTemplate(
                Object.assign({}, this._ctx, {
                    post: post,
                    name: sideName,
                    editable: isEditable,
                })
            )
        );

        let postIdNode = sideNode.querySelector("input[type=text]");
        let searchButtonNode = sideNode.querySelector("input[type=button]");
        if (isEditable) {
            postIdNode.addEventListener("keydown", (e) =>
                this._evtPostSearchFieldKeyDown(e)
            );
            searchButtonNode.addEventListener("click", (e) =>
                this._evtPostSearchButtonClick(e, postIdNode)
            );
        }
    }
    
    _setPostField(num) {
        this._rightSideNode.querySelector("input#merge-id-right").value = num;
        this._rightSideNode.querySelector("header > input[type='button']").click();
    }

    _evtSubmit(e) {
        e.preventDefault();
        const checkedTargetPost = this._formNode.querySelector(
            ".target-post :checked"
        ).value;
        const checkedTargetPostContent = this._formNode.querySelector(
            ".target-post-content :checked"
        ).value;
        this.dispatchEvent(
            new CustomEvent("submit", {
                detail: {
                    post:
                        checkedTargetPost === "left"
                            ? this._rightPost
                            : this._leftPost,
                    targetPost:
                        checkedTargetPost === "left"
                            ? this._leftPost
                            : this._rightPost,
                    useOldContent:
                        checkedTargetPostContent !== checkedTargetPost,
                },
            })
        );
    }

    _evtPostSearchFieldKeyDown(e) {
        const key = e.which;
        if (key !== KEY_RETURN) {
            return;
        }
        e.target.blur();
        e.preventDefault();
        this.dispatchEvent(
            new CustomEvent("select", {
                detail: {
                    postId: e.target.value,
                },
            })
        );
    }

    _evtPostSearchButtonClick(e, textNode) {
        e.target.blur();
        e.preventDefault();
        this.dispatchEvent(
            new CustomEvent("select", {
                detail: {
                    postId: textNode.value,
                },
            })
        );
    }

    get _formNode() {
        return this._hostNode.querySelector("form");
    }

    get _leftSideNode() {
        return this._hostNode.querySelector(".left-post-container");
    }

    get _rightSideNode() {
        return this._hostNode.querySelector(".right-post-container");
    }
}

module.exports = PostMergeView;
