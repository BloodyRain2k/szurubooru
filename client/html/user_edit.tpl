<div id='user-edit'>
    <form>
        <input class='anticomplete' type='text' name='fakeuser'/>
        <input class='anticomplete' type='password' name='fakepass'/>

        <ul class='input'>
            <% if (ctx.canEditName) { %>
                <li>
                    <%= ctx.makeTextInput({
                        text: 'User name',
                        name: 'name',
                        value: ctx.user.name,
                        pattern: ctx.userNamePattern,
                    }) %>
                </li>
            <% } %>

            <% if (ctx.canEditPassword) { %>
                <li>
                    <%= ctx.makePasswordInput({
                        text: 'Password',
                        name: 'password',
                        placeholder: 'leave blank if not changing',
                        pattern: ctx.passwordPattern,
                    }) %>
                </li>
            <% } %>

            <% if (ctx.canEditEmail) { %>
                <li>
                    <%= ctx.makeEmailInput({
                        text: 'Email',
                        name: 'email',
                        value: ctx.user.email,
                    }) %>
                </li>
            <% } %>

            <% if (ctx.canEditRank) { %>
                <li>
                    <%= ctx.makeSelect({
                        text: 'Rank',
                        name: 'rank',
                        keyValues: ctx.ranks,
                        selectedKey: ctx.user.rank,
                    }) %>
                </li>
            <% } %>

            <% if (ctx.canEditAvatar) { %>
                <li class='avatar'>
                    <label>Avatar</label>
                    <div id='avatar-content'></div>
                    <div id='avatar-radio'>
                        <% if (ctx.user.avatarStyle.substring(0, 4) == 'mood') { %>
                            <%= ctx.makeRadio({
                                text: 'Mood',
                                name: 'avatar-style',
                                value: ctx.user.avatarStyle,
                                selectedValue: ctx.user.avatarStyle,
                            }) %>
                        <% } else { %>
                            <%= ctx.makeRadio({
                                text: 'Mood',
                                name: 'avatar-style',
                                value: 'mood_5',
                                selectedValue: ctx.user.avatarStyle,
                            }) %>
                        <% } %>

                        <%= ctx.makeRadio({
                            text: 'Gravatar',
                            name: 'avatar-style',
                            value: 'gravatar',
                            selectedValue: ctx.user.avatarStyle,
                        }) %>

                        <%= ctx.makeRadio({
                            text: 'Manual avatar',
                            name: 'avatar-style',
                            value: 'manual',
                            selectedValue: ctx.user.avatarStyle,
                        }) %>
                    </div>
                </li>
            <% } %>
        </ul>

        <div class='messages'></div>

        <div class='buttons'>
            <input type='submit' value='Save settings'/>
        </div>
    </form>
</div>
