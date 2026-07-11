# Google Documentation Guide

> Fetched from Google's public style guides during `specreg init`.
> License: CC BY 3.0, as stated by Google Style Guides.
> Fetched at: 2026-07-11T02:20:42.883Z

## Overview

Source: https://google.github.io/styleguide/docguide/

Google documentation guide | styleguide


-


-

-


# [styleguide](https://google.github.io/styleguide/)


# Google documentation guide


- [Markdown styleguide](/styleguide/docguide/style.html)


- [Best practices](/styleguide/docguide/best_practices.html)


- [README files](/styleguide/docguide/READMEs.html)


- [Philosophy](/styleguide/docguide/philosophy.html)


## See also


- [How to update this guide](https://goto.google.com/doc-guide), for Googlers.


        This site is open source. [Improve this page](https://github.com/google/styleguide/edit/gh-pages/docguide/README.md).

## Markdown style guide

Source: https://google.github.io/styleguide/docguide/style.html

Markdown style guide | styleguide


-


-

-


# [styleguide](https://google.github.io/styleguide/)


# Markdown style guide


Much of what makes Markdown refreshing is the ability to write plain text and get
great formatted output as a result. To keep the slate clean for the next author,
your Markdown should be simple and consistent with the whole corpus wherever
possible.


We seek to balance three goals:


- Source text is readable and portable.


- The Markdown corpus is maintainable over time and across teams.


- The syntax is simple and easy to remember.


Contents:


- [Minimum viable documentation](#minimum-viable-documentation)


- [Better is better than best](#better-is-better-than-best)


- [Capitalization](#capitalization)


- [Document layout](#document-layout)


- [Table of contents](#table-of-contents)


- [Character line limit](#character-line-limit)


- [Trailing whitespace](#trailing-whitespace)


- [Headings](#headings)


- [ATX-style headings](#atx-style-headings)


- [Use unique, complete names for headings](#use-unique-complete-names-for-headings)


- [Add spacing to headings](#add-spacing-to-headings)


- [Use a single H1 heading](#use-a-single-h1-heading)


- [Capitalization of titles and headers](#capitalization-of-titles-and-headers)


- [Lists](#lists)


- [Use lazy numbering for long lists](#use-lazy-numbering-for-long-lists)


- [Nested list spacing](#nested-list-spacing)


- [Code](#code)


- [Inline](#inline)


- [Use code span for escaping](#use-code-span-for-escaping)


- [Codeblocks](#codeblocks)


- [Declare the language](#declare-the-language)


- [Escape newlines](#escape-newlines)


- [Use fenced code blocks instead of indented code blocks](#use-fenced-code-blocks-instead-of-indented-code-blocks)


- [Nest codeblocks within lists](#nest-codeblocks-within-lists)


- [Links](#links)


- [Use explicit paths for links within Markdown](#use-explicit-paths-for-links-within-markdown)


- [Avoid relative paths unless within the same directory](#avoid-relative-paths-unless-within-the-same-directory)


- [Use informative Markdown link titles](#use-informative-markdown-link-titles)


- [Reference links](#reference-links)


- [Use reference links for long links](#use-reference-links-for-long-links)


- [Use reference links to reduce duplication](#use-reference-links-to-reduce-duplication)


- [Define reference links after their first use](#define-reference-links-after-their-first-use)


- [Images](#images)


- [Tables](#tables)


- [Strongly prefer Markdown to HTML](#strongly-prefer-markdown-to-html)


## Minimum viable documentation


A small set of fresh and accurate docs is better than a sprawling, loose
assembly of “documentation” in various states of disrepair.


The Markdown way encourages engineers to take ownership of their docs and
keep them up to date with the same zeal we keep our tests in good order. Strive
for this.


- Identify what you really need: release docs, API docs, testing guidelines.


- Delete cruft frequently and in small batches.


## Better is better than best


The standards for an internal documentation review are different from the
standards for code reviews. Reviewers should ask for improvements, but in
general, the author should always be able to invoke the “Better/Best Rule.”


Fast iteration is your friend. To get long-term improvement, authors must stay
productive when making short-term improvements. Set lower standards for each
CL, so that more such CLs can happen.


As a reviewer of a documentation CL:


- When reasonable, LGTM immediately and trust that comments will be fixed
appropriately.


- Prefer to suggest an alternative rather than leaving a vague comment.


- For substantial changes, start your own follow-up CL instead. Especially try
to avoid comments of the form “You should also…”.


- On rare occasions, hold up submission if the CL actually makes the docs
worse. It’s okay to ask the author to revert.


As an author:


- Avoid wasting cycles with trivial argument. Capitulate early and move on.


- Cite the Better/Best Rule as often as needed.


## Capitalization


Use the original names of products, tools and binaries, preserving the
capitalization. E.g.:


`# Markdown style guide

`Markdown` is a dead-simple platform for internal engineering documentation.
`


and not


`# markdown bad style guide example

`markdown` is a dead-simple platform for internal engineering documentation.
`


## Document layout


In general, documents benefit from some variation of the following layout:


`# Document Title

Short introduction.

[TOC]

## Topic

Content.

## See also

* https://link-to-more-info
`


-
    `# Document title`: The first heading should be a level-one heading, ideally
the same or nearly the same as the filename. The first level-one heading is
used as the page `<title>`.


-
    `author`: Optional. If you’d like to claim ownership of the document or
if you are very proud of it, add yourself under the title. However,
revision history generally suffices.


-
    `Short introduction.` 1–3 sentences providing a high-level overview of the
topic. Imagine yourself as a complete newbie who landed on your “Extending Foo” doc
and doesn’t know the most basic information you take for granted. “What is
Foo? Why would I extend it?”


-
    `[TOC]`: if you use hosting that supports table of contents, such as Gitiles,
put `[TOC]` after the short introduction. See [[TOC] documentation](https://gerrit.googlesource.com/gitiles/+/HEAD/Documentation/markdown.md#Table-of-contents).


-
    `## Topic`: The rest of your headings should start from level 2.


-
    `## See also`: Put miscellaneous links at the bottom for the user who wants
to know more or didn’t find what they needed.


## Table of contents


### Use a `[TOC]` directive


Use a [[TOC] directive](https://gerrit.googlesource.com/gitiles/+/HEAD/Documentation/markdown.md#Table-of-contents) unless all
of your content is above the fold[1](#fn:above) on a laptop.


### Place the `[TOC]` directive after the introduction


Place the `[TOC]` directive after your page’s introduction and before the first
H2 heading. For example:


`# My Page

This is my introduction **before** the TOC.

[TOC]

## My first H2
`


`# My Page

[TOC]

This is my introduction **after** the TOC where it should not be.

## My first H2
`


For users who read your documentation visually, it doesn’t matter where your
`[TOC]` directive is placed, as Markdown always displays the TOC toward the top and
to the right of the page. However, `[TOC]` placement matters a lot when screen
readers or keyboard controls are involved.


That’s because `[TOC]` inserts the HTML for the table of contents into the DOM
wherever you’ve included the directive in your Markdown file. If, for example,
you place the directive at the very bottom of your file, screen readers won’t
read it until they get to the end of the document.


## Character line limit


Markdown content follows the residual convention of an 80-character line limit.
Why? Because it’s what most of us do for code.


-
    Tooling integration: All our tooling is designed around code, so the
more our documents are formatted according to similar rules, the better
these tools will work. For example, Code Search doesn’t soft wrap.


-
    Quality. The more engineers use their well-worn coding habits when
creating and editing Markdown content, the better the quality. Markdown takes
advantage of the excellent review culture we already have.


### Exceptions


Exceptions to the 80-character rule include:


- Links


- Tables


- Headings


- Code blocks


This means that lines with links are allowed to extend past column 80, along
with any relevant punctuation:


`*   See the
    [foo docs](https://gerrit.googlesource.com/gitiles/+/HEAD/Documentation/markdown.md).
    and find the logfile.
`


However, note that text before and after the link gets wrapped.


Tables may also run long. However, there are
[best practices for creating short, readable tables](#tables).


`Foo                                                                           | Bar | Baz
----------------------------------------------------------------------------- | --- | ---
Somehow-unavoidable-long-cell-filled-with-content-that-simply-refuses-to-wrap | Foo | Bar
`


## Trailing whitespace


Don’t use trailing whitespace. Use a trailing backslash to break lines.


The [CommonMark spec](http://spec.commonmark.org/0.20/#hard-line-breaks) decrees
that two spaces at the end of a line should insert a `<br />` tag. However, many
directories have a presubmit check for trailing whitespace, and many IDEs will
clean it up anyway.


Use a trailing backslash, sparingly:


`For some reason I just really want a break here,\
though it's probably not necessary.
`


Best practice is to avoid the need for a `<br />` altogether. A pair of newlines
will create a paragraph tag; get used to that.


## Headings


### ATX-style headings


`# Heading 1

## Heading 2
`


Headings with `=` or `-` underlines can be annoying to maintain and don’t fit
with the rest of the heading syntax. An editor has to ask: Does `---` mean H1 or
H2?


`Heading - do you remember what level? DO NOT DO THIS.
---------
`


### Use unique, complete names for headings


Use unique and fully descriptive names for each heading, even for sub-sections.
Since link anchors are constructed from headings, this helps ensure that the
automatically-constructed anchor links are intuitive and clear.


For example, instead of:


`## Foo
### Summary
### Example
## Bar
### Summary
### Example
`


prefer:


`## Foo
### Foo summary
### Foo example
## Bar
### Bar summary
### Bar example
`


### Add spacing to headings


Prefer spacing after `#` and newlines before and after:


`...text before.

## Heading 2

Text after...
`


Lack of spacing makes it a little harder to read in source:


`...text before.

##Heading 2
Text after... DO NOT DO THIS.
`


### Use a single H1 heading


Use one H1 heading as the title of your document. Subsequent headings should be
H2 or deeper. See [Document layout](#document-layout) for more information.


### Capitalization of titles and headers


Follow the guidance for
[capitalization](https://developers.google.com/style/capitalization#capitalization-in-titles-and-headings)
in the
[Google Developer Documentation Style Guide](https://developers.google.com/style/).


## Lists


### Use lazy numbering for long lists


Markdown is smart enough to let the resulting HTML render your numbered lists
correctly. For longer lists that may change, especially long nested lists, use
“lazy” numbering:


`1.  Foo.
1.  Bar.
    1.  Foofoo.
    1.  Barbar.
1.  Baz.
`


However, if the list is small and you don’t anticipate changing it, prefer fully
numbered lists, because it’s nicer to read in source:


`1.  Foo.
2.  Bar.
3.  Baz.
`


### Nested list spacing


When nesting lists, use a 4-space indent for both numbered and bulleted lists:


`1.  Use 2 spaces after the item number, so the text itself is indented 4 spaces.
    Use a 4-space indent for wrapped text.
2.  Use 2 spaces again for the next item.

*   Use 3 spaces after a bullet, so the text itself is indented 4 spaces.
    Use a 4-space indent for wrapped text.
    1.  Use 2 spaces with numbered lists, as before.
        Wrapped text in a nested list needs an 8-space indent.
    2.  Looks nice, doesn't it?
*   Back to the bulleted list, indented 3 spaces.
`


The following works, but it’s very messy:


`* One space,
with no indent for wrapped text.
     1. Irregular nesting... DO NOT DO THIS.
`


Even when there’s no nesting, using the 4 space indent makes layout consistent
for wrapped text:


`*   Foo,
    wrapped with a 4-space indent.

1.  Two spaces for the list item
    and 4 spaces before wrapped text.
2.  Back to 2 spaces.
`


However, when lists are small, not nested, and a single line, one space can
suffice for both kinds of lists:


`* Foo
* Bar
* Baz.

1. Foo.
2. Bar.
`


## Code


### Inline


`Backticks` designate `inline code` that will be rendered literally. Use
them for short code quotations, field names, and more:


`You'll want to run `really_cool_script.sh arg`.

Pay attention to the `foo_bar_whammy` field in that table.
`


Use inline code when referring to file types in a generic sense, rather than a
specific existing file:


`Be sure to update your `README.md`!
`


### Use code span for escaping


When you don’t want text to be processed as normal Markdown, like a fake path or
example URL that would lead to a bad autolink, wrap it in backticks:


`An example Markdown shortlink would be: `Markdown/foo/Markdown/bar.md`

An example query might be: `https://www.google.com/search?q=$TERM`
`


### Codeblocks


For code quotations longer than a single line, use a fenced code block:


```python
def Foo(self, bar):
  self.bar = bar
```


#### Declare the language


It is best practice to explicitly declare the language, so that neither the
syntax highlighter nor the next editor must guess.


#### Use fenced code blocks instead of indented code blocks


Four-space indenting is also interpreted as a code block. However, we strongly
recommend fencing for all code blocks.


Indented code blocks can sometimes look cleaner in the source, but they have
several drawbacks:


- You cannot specify the language. Some Markdown features are tied to language
specifiers.


- The beginning and end of the code block are ambiguous.


- Indented code blocks are harder to search for in Code Search.


`You'll need to run:

    bazel run :thing -- --foo

And then:

    bazel run :another_thing -- --bar

And again:

    bazel run :yet_again -- --baz
`


#### Escape newlines


Because most command-line snippets are intended to be copied and pasted directly
into a terminal, it’s best practice to escape any newlines. Use a single
backslash at the end of the line:


```shell
$ bazel run :target -- --flag --foo=longlonglonglonglongvalue \
  --bar=anotherlonglonglonglonglonglonglonglonglonglongvalue
```


#### Nest codeblocks within lists


If you need a code block within a list, make sure to indent it so as to not
break the list:


`*   Bullet.

    ```c++
    int foo;
    ```

*   Next bullet.
`


You can also create a nested code block with 4 spaces. Simply indent 4
additional spaces from the list indentation:


`*   Bullet.

        int foo;

*   Next bullet.
`


## Links


Long links make source Markdown difficult to read and break the 80 character
wrapping. Wherever possible, shorten your links.


### Use explicit paths for links within Markdown


Use the explicit path for Markdown links. For example:


`[...](/path/to/other/markdown/page.md)
`


You don’t need to use the entire qualified URL:


`[...](https://bad-full-url.example.com/path/to/other/markdown/page.md)
`


### Avoid relative paths unless within the same directory


Relative paths are fairly safe within the same directory. For example:


`[...](other-page-in-same-dir.md)
[...](/path/to/another/dir/other-page.md)
`


Avoid relative links if you need to specify other directories with `../`:


`[...](../../bad/path/to/another/dir/other-page.md)
`


### Use informative Markdown link titles


Markdown link syntax allows you to set a link title. Use it wisely. Users often
do not read documents; they scan them.


Links catch the eye. But titling your links “here,” “link,” or simply
duplicating the target URL tells the hasty reader precisely nothing and is a
waste of space:


`DO NOT DO THIS.

See the Markdown guide for more info: [link](markdown.md), or check out the
style guide [here](/styleguide/docguide/style.html).

Check out a typical test result:
[https://example.com/foo/bar](https://example.com/foo/bar).
`


Instead, write the sentence naturally, then go back and wrap the most
appropriate phrase with the link:


`See the [Markdown guide](markdown.md) for more info, or check out the
[style guide](/styleguide/docguide/style.html).

Check out a
[typical test result](https://example.com/foo/bar).
`


### Reference


For long links or image URLs, you may want to split the link use from the link
definition, like this:


`See the [Markdown style guide][style], which has suggestions for making docs more
readable.

﻿[style]: http://Markdown/corp/Markdown/docs/reference/style.md
`


#### Use reference links for long links


Use reference links where the length of the link would detract from the
readability of the surrounding text if it were inlined. Reference links make it
harder to see the destination of a link in source text, and add additional
syntax.


In this example, reference link usage is not appropriate, because the link is
not long enough to disrupt the flow of the text:


`DO NOT DO THIS.

The [style guide][style_guide] says not to use reference links unless you have
to.

﻿[style_guide]: https://google.com/Markdown-style
`


Just inline it instead:


`https://google.com/Markdown-style says not to use reference links unless you have to.
`


In this example, the link destination is long enough that it makes sense to use
a reference link:


`The [style guide] says not to use reference links unless you have to.

﻿[style guide]: https://docs.google.com/document/d/13HQBxfhCwx8lVRuN2Wf6poqvAfVeEXmFVcawP5I6B3c/edit
`


Use reference links more often in tables. It is particularly important to keep
table content short, since Markdown does not provide a facility to break text in
cell tables across multiple lines, and smaller tables are more readable.


For example, this table’s readability is worsened by inline links:


`DO NOT DO THIS.

Site                                                             | Description
---------------------------------------------------------------- | -----------------------
[site 1](http://google.com/excessively/long/path/example_site_1) | This is example site 1.
[site 2](http://google.com/excessively/long/path/example_site_2) | This is example site 2.
`


Instead, use reference links to keep the line length manageable:


`Site     | Description
-------- | -----------------------
[site 1] | This is example site 1.
[site 2] | This is example site 2.

﻿[site 1]: http://google.com/excessively/long/path/example_site_1
﻿[site 2]: http://google.com/excessively/long/path/example_site_2
`


#### Use reference links to reduce duplication


Consider using reference links when referencing the same link destination
multiple times in a document, to reduce duplication.


#### Define reference links after their first use


We recommend putting reference link definitions just before the next heading, at
the end of the section in which they’re first used. If your editor has its own
opinion about where they should go, don’t fight it; the tools always win.


We define a “section” as all text between two headings. Think of reference links
like footnotes, and the current section like the current page.


This arrangement makes it easy to find the link destination in source view,
while keeping the flow of text free from clutter. In long documents with lots of
reference links, it also prevents “footnote overload” at the bottom of the file,
which makes it difficult to pick out the relevant link destination.


There is one exception to this rule: reference link definitions that are used in
multiple sections should go at the end of the document. This avoids dangling
links when a section is updated or moved.


In the following example, the reference definition is far from its initial use,
which makes the document harder to read:


`# Header FOR A BAD DOCUMENT

Some text with a [link][link_def].

Some more text with the same [link][link_def].

## Header 2

... lots of text ...

## Header 3

Some more text using a [different_link][different_link_def].

﻿[link_def]: http://reallyreallyreallylonglink.com
﻿[different_link_def]: http://differentreallyreallylonglink.com
`


Instead, put it just before the header following its first use:


`# Header

Some text with a [link][link_def].

Some more text with the same [link][link_def].

﻿[link_def]: http://reallyreallyreallylonglink.com

## Header 2

... lots of text ...

## Header 3

Some more text using a [different_link][different_link_def].

﻿[different_link_def]: http://differentreallyreallylonglink.com
`


## Images


See [image syntax](https://gerrit.googlesource.com/gitiles/+/HEAD/Documentation/markdown.md#Images).


Use images sparingly, and prefer simple screenshots. This guide is designed
around the idea that plain text gets users down to the business of communication
faster with less reader distraction and author procrastination. However, it’s
sometimes very helpful to show what you mean.


- Use images when it’s easier to show a reader something than to describe
it. For example, explaining how to navigate a UI is often easier with an
image than text.


- Make sure to provide appropriate text to describe your image. Readers who
are not sighted cannot see your image and still need to understand the
content! See the alt text best practices below.


## Tables


Use tables when they make sense: for the presentation of tabular data that needs
to be scanned quickly.


Avoid using tables when your data could easily be presented in a list. Lists are
much easier to write and read in Markdown.


For example:


`DO NOT DO THIS

Fruit  | Metrics      | Grows on | Acute curvature    | Attributes                                                                                                  | Notes
------ | ------------ | -------- | ------------------ | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------
Apple  | Very popular | Trees    |                    | [Juicy](http://cs/SomeReallyReallyReallyReallyReallyReallyReallyReallyLongQuery), Firm, Sweet               | Apples keep doctors away.
Banana | Very popular | Trees    | 16 degrees average | [Convenient](http://cs/SomeDifferentReallyReallyReallyReallyReallyReallyReallyReallyLongQuery), Soft, Sweet | Contrary to popular belief, most apes prefer mangoes. Don't you? See the [design doc][banana_v2] for the newest hotness in bananiels.
`


This table illustrates a few typical problems:


-
    Poor distribution: Several columns don’t differ across rows, and some
cells are empty. This is usually a sign that your data may not benefit from
tabular display.


-
    Unbalanced dimensions: There are a small number of rows relative to
columns. When this ratio is unbalanced in either direction, a table becomes
little more than an inflexible format for text.


-
    Rambling prose in some cells. Tables should tell a succinct story at a
glance.


[Lists](#lists) and subheadings sometimes suffice to present the same
information. Let’s see this data in list form:


`## Fruits

Both types are highly popular, sweet, and grow on trees.

### Apple

*   [Juicy](http://SomeReallyReallyReallyReallyReallyReallyReallyReallyReallyReallyReallyReallyReallyReallyReallyReallyLongURL)
*   Firm

Apples keep doctors away.

### Banana

*   [Convenient](http://cs/SomeDifferentReallyReallyReallyReallyReallyReallyReallyReallyLongQuery)
*   Soft
*   16 degrees average acute curvature.

Contrary to popular belief, most apes prefer mangoes. Don't you?

See the [design doc][banana_v2] for the newest hotness in bananiels.
`


The list form is more spacious, and arguably therefore much easier for the
reader to find what interests her in this case.


However, there are times a table is the best choice. When you have:


- Relatively uniform data distribution across two dimensions.


- Many parallel items with distinct attributes.


In those cases, a table format is just the thing. In fact, a compact table can
improve readability:


`Transport        | Favored by     | Advantages
---------------- | -------------- | -----------------------------------------------
Swallow          | Coconuts       | [Fast when unladen][airspeed]
Bicycle          | Miss Gulch     | [Weatherproof][tornado_proofing]
X-34 landspeeder | Whiny farmboys | [Cheap][tosche_station] since the XP-38 came out

﻿[airspeed]: http://google3/airspeed.h
﻿[tornado_proofing]: http://google3/kansas/
﻿[tosche_station]: http://google3/power_converter.h
`


Note that [reference links](#reference-links) are used to keep the table cells
manageable.


## Strongly prefer Markdown to HTML


Please prefer standard Markdown syntax wherever possible and avoid HTML hacks.
If you can’t seem to accomplish what you want, reconsider whether you really
need it. Except for [big tables](#tables), Markdown meets almost all needs
already.


Every bit of HTML hacking reduces the readability and portability of our
Markdown corpus. This in turn limits the usefulness of integrations with other
tools, which may either present the source as plain text or render it. See
[Philosophy](/styleguide/docguide/philosophy.html).


Gitiles does not render HTML.


-
      Content is “above the fold” if it is visible when the page is first
displayed. Content is “below the fold” if it is hidden until the user
scrolls down the page on a computer or literally unfolds a document
such as a newspaper. [↩](#fnref:above)


        This site is open source. [Improve this page](https://github.com/google/styleguide/edit/gh-pages/docguide/style.md).

## Documentation best practices

Source: https://google.github.io/styleguide/docguide/best_practices.html

Documentation Best Practices | styleguide


-


-

-


# [styleguide](https://google.github.io/styleguide/)


# Documentation Best Practices


“Say what you mean, simply and directly.” -
[Brian Kernighan](https://en.wikipedia.org/wiki/The_Elements_of_Programming_Style)


Contents:


- [Minimum Viable Documentation](#minimum-viable-documentation)


- [Update Docs with Code](#update-docs-with-code)


- [Delete Dead Documentation](#delete-dead-documentation)


- [Prefer the Good Over the Perfect](#prefer-the-good-over-the-perfect)


- [Documentation is the Story of Your Code](#documentation-is-the-story-of-your-code)


- [Duplication is Evil](#duplication-is-evil)


## Minimum Viable Documentation


A small set of fresh and accurate docs is better than a large assembly of
“documentation” in various states of disrepair.


Write short and useful documents. Cut out everything unnecessary, including
out-of-date, incorrect, or redundant information. Also make a habit of
continually massaging and improving every doc to suit your changing needs.
Docs work best when they are alive but frequently trimmed, like a bonsai
tree.


See also
[these Agile Documentation best practices](https://www.agilemodeling.com/essays/agileDocumentationBestPractices.htm).


## Update Docs with Code


Change your documentation in the same CL as the code change. This keeps your
docs fresh, and is also a good place to explain to your reviewer what you’re
doing.


A good reviewer can at least insist that docstrings, header files, README.md
files, and any other docs get updated alongside the CL.


## Delete Dead Documentation


Dead docs are bad. They misinform, they slow down, they incite despair in
engineers and laziness in team leads. They set a precedent for leaving behind
messes in a code base. If your home is clean, most guests will be clean without
being asked.


Just like any big cleaning project, it’s easy to be overwhelmed. If your
docs are in bad shape:


- Take it slow, doc health is a gradual accumulation.


- First delete what you’re certain is wrong, ignore what’s unclear.


- Get your whole team involved. Devote time to quickly scan every doc and make
a simple decision: Keep or delete?


- Default to delete or leave behind if migrating. Stragglers can always be
recovered.


- Iterate.


## Prefer the Good Over the Perfect


Documentation is an art. There is no perfect document, there are only proven
methods and prudent guidelines. See [Better is better than best](/styleguide/docguide/style.html).


## Documentation is the Story of Your Code


Writing excellent code doesn’t end when your code compiles or even if your test
coverage reaches 100%. It’s easy to write something a computer understands, it’s
much harder to write something both a human and a computer understand. Your
mission as a Code Health-conscious engineer is to write for humans first,
computers second. Documentation is an important part of this skill.


There’s a spectrum of engineering documentation that ranges from terse comments
to detailed prose:


-
    Meaningful names: Good naming allows the code to convey information that
would otherwise be relegated to comments or documentation. This includes
nameable entities at all levels, from local variables to classes, files, and
directories.


-
    Inline comments: The primary purpose of inline comments is to provide
information that the code itself cannot contain, such as why the code is
there.


-
    Method and class comments:


-
        Method API documentation: The header / Javadoc / docstring comments
that say what methods do and how to use them. This documentation is
the contract of how your code must behave. The intended audience is
future programmers who will use and modify your code.


        It is often reasonable to say that any behavior documented here should
have a test verifying it. This documentation details what arguments the
method takes, what it returns, any “gotchas” or restrictions, and what
exceptions it can throw or errors it can return. It does not usually
explain why code behaves a particular way unless that’s relevant to a
developer’s understanding of how to use the method. “Why” explanations
are for inline comments. Think in practical terms when writing method
documentation: “This is a hammer. You use it to pound nails.”


-
        Class / Module API documentation: The header / Javadoc / docstring
comments for a class or a whole file. This documentation gives a brief
overview of what the class / file does and often gives a few short
examples of how you might use the class / file.


        Examples are particularly relevant when there’s several distinct ways to
use the class (some advanced, some simple). Always list the simplest use
case first.


-
    README.md: A good README.md orients the new user to the directory and
points to more detailed explanation and user guides:


- What is this directory intended to hold?


- Which files should the developer look at first? Are some files an API?


- Who maintains this directory and where I can learn more?


    See the [README.md guidelines](/styleguide/docguide/READMEs.html).


-
    docs: The contents of a good docs directory explain how to:


- Get started using the relevant API, library, or tool.


- Run its tests.


- Debug its output.


- Release the binary.


-
    Design docs, PRDs: A good design doc or PRD discusses the proposed
implementation at length for the purpose of collecting feedback on that
design. However, once the code is implemented, design docs should serve as
archives of these decisions, not as half-correct docs (they are often
misused).


-
    Other external docs: Some teams maintain documentation in other
locations, separate from the code, such as Google Sites, Drive, or wiki.
If you do maintain documentation in
other locations, you should clearly point to those locations from your
project directory (for example, by adding an obvious link to the location
from your project’s `README.md`).


## Duplication is Evil


Do not write your own guide to a common Google technology or process. Link to it
instead. If the guide doesn’t exist or it’s badly out of date, submit your
updates to the appropriate directory or create a package-level
README.md. Take ownership and don’t be shy: Other teams will usually welcome
your contributions.


        This site is open source. [Improve this page](https://github.com/google/styleguide/edit/gh-pages/docguide/best_practices.md).

## README files

Source: https://google.github.io/styleguide/docguide/READMEs.html

READMEs | styleguide


-


-

-


# [styleguide](https://google.github.io/styleguide/)


# READMEs


About README.md files.


- [Overview](#overview)


- [Readable README files](#readable-readme-files)


- [Where to put your README](#where-to-put-your-readme)


- [What to put in your README](#what-to-put-in-your-readme)


## Overview


A README is a short summary of the contents of a directory. The contents of the
file are displayed in GitHub and Gitiles when you view the contents of the
containing directory. README files provide critical information for people
browsing your code, especially first-time users.


This document covers how to create README files that are readable with GitHub
and Gitiles.


## Readable README files


README files must be named `README.md`. The file name must end with the
`.md` extension and is case sensitive.


For example, the file /README.md is rendered when you view the contents of the
containing directory:


https://github.com/google/styleguide/tree/gh-pages


Also `README.md` at `HEAD` ref is rendered by Gitiles when displaying repository
index:


https://gerrit.googlesource.com/gitiles/


## Where to put your README


Unlike all other Markdown files, `README.md` files should not be located inside
your product or library’s documentation directory. `README.md` files should be
located in the top-level directory for your product or library’s actual
codebase.


All top-level directories for a code package should have an up-to-date
`README.md` file. This is especially important for package directories that
provide interfaces for other teams.


## What to put in your README


At a minimum, your `README.md` file should contain a link to your user- and/or
team-facing documentation.


Every package-level `README.md` should include or point to the following
information:


- What is in this package or library and what’s it used for.


- Points of contact.


- Status of whether this package or library is deprecated, or not for general
release, etc.


- How to use the package or library. Examples include sample code, copyable
`bazel run` or `bazel test` commands, etc.


- Links to relevant documentation.


        This site is open source. [Improve this page](https://github.com/google/styleguide/edit/gh-pages/docguide/READMEs.md).

## Philosophy

Source: https://google.github.io/styleguide/docguide/philosophy.html

Philosophy | styleguide


-


-

-


# [styleguide](https://google.github.io/styleguide/)


# Philosophy


埏埴以為器，當其無，有器之用.


Clay becomes pottery through craft, but it’s the emptiness that makes a pot
useful.


- [Laozi](https://ctext.org/dictionary.pl?if=en&id=11602)


Contents:


- [Radical simplicity](#radical-simplicity)


- [Readable source text](#readable-source-text)


- [Minimum viable documentation](#minimum-viable-documentation)


- [Better is better than best](#better-is-better-than-best)


## Radical simplicity


-
    Scalability and interoperability are more important than a menagerie of
unessential features. Scale comes from simplicity, speed, and ease.
Interoperability comes from unadorned, digestible content.


-
    Fewer distractions make for better writing and more productive reading.


-
    New features should never interfere with the simplest use case and
should remain invisible to users who don’t need them.


-
    Markdown is designed for the average engineer – the busy,
just-want-to-go-back-to-coding engineer. Large and complex documentation is
possible but not the primary focus.


-
    Minimizing context switching makes people happier. Engineers should be
able to interact with documentation using the same tools they use to read
and write code.


## Readable source text


-
    Plain text not only suffices, it is superior. Markdown itself is not
essential to this formula, but it is the best and most widely supported
solution right now. HTML is generally not encouraged.


-
    Content and presentation should not mingle. It should always be possible
to ditch the renderer and read the essential information at source. Users
should never have to touch the presentation layer if they don’t want to.


-
    Portability and future-proofing leave room for the unimagined integrations
to come, and are best achieved by keeping the source as human-readable as
possible.


-
    Static content is better than dynamic, because content should not depend
on the features of any one server. However, fresh is better than stale. We
strive to balance these needs.


## Minimum viable documentation


-
    Docs thrive when they’re treated like tests: a necessary chore one learns
to savor because it rewards over time.
See [Best Practices](/styleguide/docguide/best_practices.html).


-
    Brief and utilitarian is better than long and exhaustive. The vast
majority of users need only a small fraction of the author’s total knowledge,
but they need it quickly and often.


## Better is better than best


-
    Incremental improvement is better than prolonged debate. Patience and
tolerance of imperfection allow projects to evolve organically.


-
    Don’t
[lick the cookie](https://community.redhat.com/blog/2018/09/dont-lick-the-cookie/),
pass the plate. Ideas are cheap. We’re drowning in potentially impactful
projects. Choose only those you can really handle and release those you
can’t.


        This site is open source. [Improve this page](https://github.com/google/styleguide/edit/gh-pages/docguide/philosophy.md).

