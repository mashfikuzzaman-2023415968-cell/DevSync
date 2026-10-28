# UI/UX questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/uiux.md`.

## uiux-legacy-01

Usability principles · difficulty 2 · independent solve passed

What is information architecture?

- A. Server layout
- B. How content is organised, labelled and navigated ✔
- C. Database design
- D. Typography

Explanation: Information architecture is the structure, grouping and labelling of content so people can find things and understand where they are.

Approved by: ______

Correction: ______

## uiux-legacy-03

Usability principles · difficulty 2 · independent solve passed

What does progressive disclosure mean?

- A. Showing all options at once
- B. Showing advanced options only when they are needed ✔
- C. Loading images progressively
- D. Revealing passwords

Explanation: Progressive disclosure keeps the interface simple by revealing advanced or rarely used options only when the user asks for them.

Approved by: ______

Correction: ______

## uiux-legacy-04

User research basics · difficulty 1 · independent solve passed

What is the purpose of usability testing?

- A. To check spelling
- B. To measure colour contrast
- C. To test server load
- D. To watch real users attempt tasks and find problems in the design ✔

Explanation: Usability testing observes representative users performing realistic tasks to find where the design confuses them.

Approved by: ______

Correction: ______

## uiux-legacy-05

Usability principles · difficulty 1 · independent solve passed

What is a primary benefit of a design system?

- A. Consistent, reusable components and patterns across the product ✔
- B. Faster servers
- C. Fewer users
- D. Better SEO only

Explanation: A design system provides shared components, patterns and guidelines, which keeps products consistent and speeds up design and development.

Approved by: ______

Correction: ______

## uiux-legacy-07

Accessibility · difficulty 1 · independent solve passed

What is the purpose of a visible focus indicator?

- A. Decoration
- B. Indicating errors
- C. Showing keyboard users where they are on the page ✔
- D. Loading feedback

Explanation: A visible focus indicator shows keyboard and assistive-technology users which control is active; removing it breaks keyboard navigation (WCAG 2.4.7).

Approved by: ______

Correction: ______

## uiux-legacy-08

Usability principles · difficulty 1 · independent solve passed

What is a skeleton screen?

- A. A placeholder layout shown while content loads ✔
- B. A print stylesheet
- C. A wireframe
- D. An error page

Explanation: A skeleton screen shows a placeholder of the layout while content loads, signalling progress and reducing perceived waiting time.

Approved by: ______

Correction: ______

## uiux-legacy-09

Accessibility · difficulty 1 · independent solve passed

Why respect the 'prefers-reduced-motion' setting?

- A. It improves SEO
- B. It is required by browsers
- C. It saves bandwidth
- D. Some users get dizzy or distracted by motion ✔

Explanation: prefers-reduced-motion reflects a user's OS setting. Large animations can cause dizziness or nausea for people with vestibular disorders, so reduce or remove them.

Approved by: ______

Correction: ______

## uiux-legacy-10

Layout and visual hierarchy · difficulty 1 · independent solve passed

What is the main goal of a primary button style?

- A. To show the single most important action on the screen ✔
- B. To link to help
- C. To show errors
- D. To decorate

Explanation: The primary button marks the one main action, so the screen's hierarchy tells users what to do next. Secondary actions are styled with less emphasis.

Approved by: ______

Correction: ______

## uiux-legacy-11

Usability principles · difficulty 1 · independent solve passed

Why use sentence case and clear verbs on buttons (e.g. 'Save changes')?

- A. They load faster
- B. Shorter code
- C. They say exactly what will happen when pressed ✔
- D. Browsers require it

Explanation: Clear verb labels like 'Save changes' tell users the outcome of pressing the button, unlike vague labels such as 'OK' or 'Submit'.

Approved by: ______

Correction: ______

## uiux-legacy-12

Accessibility · difficulty 1 · independent solve passed

Why should status never be shown by colour alone?

- A. It is a performance issue
- B. Colours are slow to render
- C. Colours are not allowed in forms
- D. People with colour-vision deficiencies may not perceive it; add text or icons ✔

Explanation: About 1 in 12 men has a colour-vision deficiency. Colour must be paired with text, icons or patterns (WCAG 1.4.1 Use of Colour).

Approved by: ______

Correction: ______

## uiux-legacy-13

Accessibility · difficulty 2 · independent solve passed

What minimum contrast ratio does WCAG 2.1 AA require for normal body text?

- A. 4.5:1 ✔
- B. 2:1
- C. 7:1
- D. 3:1

Explanation: WCAG 2.1 AA requires a contrast ratio of at least 4.5:1 for normal text and 3:1 for large text.

Approved by: ______

Correction: ______

## uiux-legacy-14

Usability principles · difficulty 1 · independent solve passed

A good error message should…

- A. Only show an error code
- B. Blame the user
- C. Say what went wrong and how to fix it ✔
- D. Disappear after one second

Explanation: Good error messages are specific, polite and constructive: they explain what happened and what to do next.

Approved by: ______

Correction: ______

## uiux-legacy-15

Usability principles · difficulty 1 · independent solve passed

What should an empty state include?

- A. An error code
- B. Nothing
- C. A random image only
- D. A short explanation and the next action to take ✔

Explanation: An empty state should explain what belongs there and give the next action, such as a button to create the first item.

Approved by: ______

Correction: ______

## uiux-legacy-16

Layout and visual hierarchy · difficulty 2 · independent solve passed

What does Fitts's law describe?

- A. Colour perception
- B. Memory limits
- C. Time to reach a target depends on its distance and size ✔
- D. Reading speed

Explanation: Fitts's law: the time to reach a target grows with its distance and shrinks with its size, so important targets should be large and close.

Approved by: ______

Correction: ______

## uiux-usability-01

Usability principles · difficulty 1 · independent solve passed

A project settings page has a 'Delete project' button right next to 'Edit'. Users sometimes delete projects by accident. Which change best follows usability principles?

- A. Separate the button visually and offer undo or a confirmation that names the project ✔
- B. Make Delete the primary-coloured button so it is easier to find
- C. Add a tooltip that explains what Delete does
- D. Remove all confirmations so users can work faster

Explanation: Error prevention and error recovery are core usability heuristics. Putting a destructive action apart from safe ones and offering undo or a specific confirmation reduces slips. A prominent Delete button makes accidents more likely, and a tooltip is too easy to miss.

Approved by: ______

Correction: ______

## uiux-layout-hierarchy-01

Layout and visual hierarchy · difficulty 1 · independent solve passed

Which technique most directly draws the eye to the most important element on a screen?

- A. Giving every element the same size and weight
- B. Making it noticeably larger or higher in contrast than its surroundings ✔
- C. Surrounding it with several decorative borders
- D. Setting it in a smaller font than the rest

Explanation: Visual hierarchy comes from differences in size, weight, colour and contrast. When everything looks the same nothing stands out, and decoration or smaller type does not lead the eye.

Approved by: ______

Correction: ______

## uiux-layout-hierarchy-02

Layout and visual hierarchy · difficulty 2 · independent solve passed

In a form, labels sit midway between two fields, so it is hard to tell which field each label belongs to. Which fix applies the principle of proximity?

- A. Make all labels bold
- B. Put every label and field inside a border
- C. Place each label closer to its own field than to the neighbouring field ✔
- D. Use a different colour for each label

Explanation: The Gestalt principle of proximity says elements that sit close together are perceived as a group. Moving each label nearer to its field than to the next one removes the ambiguity. Bold, borders and colour do not fix the spacing.

Approved by: ______

Correction: ______

## uiux-layout-hierarchy-03

Layout and visual hierarchy · difficulty 2 · independent solve passed

Why do design teams define a spacing scale (for example 4, 8, 16, 24 and 32 px) instead of choosing margins freely?

- A. Browsers only render spacing values that are multiples of 4
- B. It makes pages load faster
- C. It removes the need for responsive layouts
- D. It gives the layout a consistent rhythm and makes screens predictable ✔

Explanation: A limited, consistent scale of spacing values makes related elements align, creates a visible rhythm and speeds up design decisions. It has no effect on rendering limits, speed or responsiveness.

Approved by: ______

Correction: ______

## uiux-layout-hierarchy-04

Layout and visual hierarchy · difficulty 3 · independent solve passed

A card shows a title, three lines of metadata and two buttons, all in the same size, weight and colour. Users cannot tell what matters. Which redesign is best?

- A. Use two or three distinct levels of size, weight and colour, with one clearly primary action ✔
- B. Make every piece of text bold so that nothing is missed
- C. Add more content to the card to explain the hierarchy
- D. Give both buttons the same bright colour so both stand out

Explanation: A clear hierarchy ranks content: a prominent title, de-emphasised metadata and a single visually dominant primary action. Emphasising everything or competing buttons removes contrast and recreates the problem.

Approved by: ______

Correction: ______

## uiux-layout-hierarchy-05

Layout and visual hierarchy · difficulty 3 · independent solve passed

An app uses the same red for its main 'Pay now' button, for error messages and for the 'Delete' action. What is the design problem?

- A. Red buttons are never allowed to be primary
- B. Red is overloaded: it signals danger and errors, so it blurs the meaning of the primary action ✔
- C. Users cannot see red text on white backgrounds
- D. A page may use only one button colour

Explanation: Colour carries meaning. Red is widely read as error or destructive, so using it for the main positive action, and also for deletion, makes users hesitate and weakens the hierarchy. Use distinct semantic colours for primary actions and danger.

Approved by: ______

Correction: ______

## uiux-accessibility-01

Accessibility · difficulty 2 · independent solve passed

A screen reader announces only 'button' for this control. What is the right fix?

```
<button class="icon-btn">
  <svg viewBox="0 0 24 24" aria-hidden="true">...</svg>
</button>
```

- A. Add a title attribute to the svg element
- B. Increase the size of the icon
- C. Give the button an accessible name, such as aria-label="Delete message" ✔
- D. Remove the button and use a div with an onclick handler

Explanation: A button with only an icon has no text for assistive technology. An accessible name from visible or visually hidden text, or an aria-label, tells users what it does. A div without role and keyboard support would be worse, and size does not help.

Approved by: ______

Correction: ______

## uiux-accessibility-02

Accessibility · difficulty 3 · independent solve passed

A modal dialog opens, but keyboard focus stays on the page behind it, and Tab moves through hidden page controls. What is the correct behaviour?

- A. Leave focus where it is so users keep their place
- B. Move focus to the browser address bar
- C. Disable the Tab key on the whole page
- D. Move focus into the dialog, keep Tab inside it while open, and return focus to the trigger on close ✔

Explanation: Keyboard and screen-reader users must be taken into a modal, kept inside it (focus trap) and returned to the triggering element afterwards. Leaving focus behind makes the dialog unreachable and exposes content that is visually covered.

Approved by: ______

Correction: ______

## uiux-accessibility-03

Accessibility · difficulty 3 · independent solve passed

A form fails validation. Which approach makes the errors accessible to screen-reader users?

- A. Describe each error in text next to its field, link it with aria-describedby and move focus to the first error ✔
- B. Turn the invalid fields' borders red and shake them
- C. Show a toast that disappears after three seconds
- D. Show one 'Form invalid' alert at the top that does not name the fields

Explanation: Errors must be perceivable without colour or timing and tied to the field they concern. Text next to the field, programmatically associated with it, plus moving focus or announcing the error, lets assistive technology users find and fix each problem.

Approved by: ______

Correction: ______

## uiux-user-research-01

User research basics · difficulty 1 · independent solve passed

What is a user persona?

- A. A real customer who is legally bound to the product
- B. A fictional but research-based profile that represents a group of users ✔
- C. A test script for usability sessions
- D. A marketing slogan for a target audience

Explanation: Personas summarise goals, needs and behaviours of a user segment, based on research data, so teams can design for real people instead of themselves. They are not real individuals, scripts or slogans.

Approved by: ______

Correction: ______

## uiux-user-research-02

User research basics · difficulty 2 · independent solve passed

Analytics show that many users abandon checkout at the payment step. Which method best reveals why?

- A. Count page views of the payment page for another month
- B. Run an A/B test of the button colour
- C. Observe users attempting checkout in usability tests and interview them ✔
- D. Send a satisfaction survey with a 1 to 5 rating

Explanation: Analytics tell you where users drop off but not why. Watching people attempt the task and asking them about it exposes confusion, missing options or trust problems. Page counts, colour tests and generic ratings do not explain the cause.

Approved by: ______

Correction: ______

## uiux-user-research-03

User research basics · difficulty 2 · independent solve passed

Which question is best for an interview that aims to understand how freelancers currently find work?

- A. Would you use a feature that finds clients for you?
- B. Don't you think finding clients is too difficult?
- C. Do you find clients online, yes or no?
- D. Tell me about the last time you looked for a new client. ✔

Explanation: Open questions about specific past behaviour give reliable, detailed answers. Hypothetical questions are unreliable, leading questions bias the answer, and closed yes/no questions give little insight.

Approved by: ______

Correction: ______

## uiux-user-research-04

User research basics · difficulty 2 · independent solve passed

A team wants to learn how users naturally group the sections of a new help centre. Which method fits?

- A. Card sorting ✔
- B. A/B testing
- C. Heatmap analysis
- D. Accessibility audit

Explanation: In card sorting, participants group labelled cards into categories they find logical, which informs the information architecture and navigation labels. A/B tests compare variants, heatmaps show interaction on a finished page, and audits check compliance.

Approved by: ______

Correction: ______

## uiux-user-research-05

User research basics · difficulty 3 · independent solve passed

After one day an A/B test with 40 visitors shows variant B with a 12% higher sign-up rate, and a stakeholder wants to ship B immediately. What is the main problem?

- A. A/B tests must always run for exactly one year
- B. The sample is too small to tell a real difference from random variation ✔
- C. Variant B cannot win if it was shown second
- D. Sign-up rate is never a valid metric

Explanation: With so few visitors the difference is well within chance. Decide the sample size or duration beforehand and test for statistical significance before concluding. Stopping early on a lucky streak is a classic mistake.

Approved by: ______

Correction: ______

## uiux-user-research-06

User research basics · difficulty 3 · independent solve passed

In a survey, 80% of users say they would use a new 'export to PDF' feature, but analytics show almost nobody uses the existing 'export to CSV' button. What is the best next step?

- A. Build the feature immediately, because the survey is definitive
- B. Discard the survey results and rely only on analytics
- C. Observe real behaviour with interviews or tests before building, since stated wishes often differ from actual use ✔
- D. Run the survey again with more questions

Explanation: People often report preferences that do not match their behaviour. Combining what users say with what they do, and investigating the gap with observation or interviews, gives a more reliable basis than either source alone.

Approved by: ______

Correction: ______
