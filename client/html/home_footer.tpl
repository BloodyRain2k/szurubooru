<ul>
    <li><%- ctx.postCount %> posts</li>
    <span class='sep'>&nbsp;</span>
    <li><%= ctx.makeFileSize(ctx.diskUsage) %> (<%= ctx.makeFileSize(ctx.diskUsageAvg) %>)</li>
    <span class='sep'>&nbsp;</span>
    <li>Space left for ~<%= ctx.remainingAvg %> posts</li>
    <% if (ctx.version) { %>
        <span class='sep'>&nbsp;</span>
        <li>
            Build <a class='version' href='https://github.com/po5/szurubooru/tree/vb'><%- ctx.version %></a>
            <% if (ctx.buildDate) { %>
                <%- ctx.isDevelopmentMode ? " (DEV MODE)" : "" %> from <%= ctx.makeRelativeTime(ctx.buildDate) %>
            <% } %>
        </li>
    <% } %>
    <% if (ctx.canListSnapshots) { %>
	    <span class='sep'>&nbsp;</span>
    	<li><a href='<%- ctx.formatClientLink('history') %>'>History</a></li>
    <% } %>
</ul>
