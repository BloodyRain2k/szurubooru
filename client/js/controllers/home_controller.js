"use strict";

const api = require("../api.js");
const uri = require("../util/uri.js");
const config = require("../config.js");
const topNavigation = require("../models/top_navigation.js");
const HomeView = require("../views/home_view.js");
const Post = require("../models/post.js");

class HomeController {
    constructor() {
        topNavigation.activate("home");
        topNavigation.setTitle("Home");

        this._homeView = new HomeView({
            name: api.getName(),
            version: config.meta.version,
            buildDate: config.meta.buildDate,
            canListSnapshots: api.hasPrivilege("snapshots:list"),
            canListPosts: api.hasPrivilege("posts:list"),
            isDevelopmentMode: config.environment == "development",
        });

        api.fetchConfig().then(() => {
            this._homeView.setStats({
                postCount: api.getPostCount(),
                diskUsage: api.getDiskUsage(),
                diskUsageAvg: api.getDiskUsageAvg(),
                remainingAvg: api.getRemainingAvg(),
            });
        });
        
        api.get(uri.formatApiLink("featured-post")).then((response) => {
            if (response) {
                this._homeView.setFeaturedPost({ featuredPost: Post.fromResponse(response) });
            }
        })
    }

    showSuccess(message) {
        this._homeView.showSuccess(message);
    }

    showError(message) {
        this._homeView.showError(message);
    }
}

module.exports = (router) => {
    router.enter([], (ctx, next) => {
        ctx.controller = new HomeController();
    });
};
