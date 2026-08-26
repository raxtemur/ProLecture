# Reinventing Entropy | Compression is Intelligence Part 1

Duration 1939 s. Utterances 528. Chapters 7.


## [0s] On “Compression is intelligence.”

`    0.0` When you encode text into binary, it's often nice to use as little data as possible,
`    4.6` so you might naturally wonder, is there some kind of fundamental
`    8.1` limit on how efficiently text can be compressed?
`   11.5` The default encoding with ASCII is pretty inefficient.
`   14.6` Each character is represented with eight full bits.
`   17.3` If you apply a little cleverness associating more common characters with
`   20.9` smaller bit strings, you can get this down to an average of around four
`   24.5` bits per character, and then much smarter methods than that,
`   27.5` that leverage patterns among long sequences of text, can get even better still.
`   32.1` But again, what's the limit?
`   34.2` I'm guessing many of you might have heard an estimate here,
`   37.2` I will share one at the end, but much more interesting than any
`   40.5` single numerical answer is how you would even approach answering it.
`   44.3` This question dates back at least to the 1940s,
`   46.6` with Claude Shannon's seminal work that kicked off information theory.
`   50.1` Now what's very interesting is how the math that he developed to answer questions
`   54.5` like this has turned out to be surprisingly useful for modern machine learning.
`   59.6` To take the salient example of today, when large language models are trained,
`   63.9` the pre-training portion of that is usually described as being about next
`   68.0` token prediction, specifically using something called cross-entropy loss.
`   72.6` Now that term, cross-entropy, has its roots in information theory.
`   75.7` But what's also interesting is that one of the conclusions of information
`   79.4` theory says that prediction and compression are mathematically equivalent.
`   83.8` They turn out to be two sides of the same coin.
`   86.4` Which means, you can entirely reframe how you think about the pre-training
`   90.3` objective as not really being about next token prediction per se,
`   93.8` but instead as being about creating the most efficient possible text compressor.
`   98.5` Later I'll explain exactly how that works, but when you do,
`  101.3` I think it offers more clarity on what this notion of cross-entropy really is,
`  105.2` and why you're using it.
`  106.8` Also, I don't know about you, but to me at least,
`  109.2` there's just something very intriguing about using compression as a fundamental
`  113.0` objective while pursuing intelligence.
`  115.5` In fact, some people have gone so far as to say, compression is intelligence.
`  120.7` Now, as stated, that's a hard claim to judge rigorously,
`  123.6` since intelligence is such a squishy and ill-defined term.
`  126.7` The safer claim would be that the mathematical theory of
`  129.9` compression is bizarrely relevant to artificial intelligence.
`  134.2` Still, the pithy phrase is thought-provoking, so this is the
`  137.4` first in a trilogy of videos aimed at laying down the mathematical
`  141.1` fundamentals to assess what this claim is really getting at.
`  144.9` For the next 30 minutes or so, you and I will be focused on understanding
`  148.5` the limits of compression, and seeing if we can get you to feel like you
`  152.1` could have rediscovered the core idea behind Shannon's noiseless coding theorem.
`  156.1` Doing so involves rediscovering a few key definitions,
`  159.4` namely those of information and entropy.
`  162.4` And it might sound a little weird for me to describe definitions as something to be
`  166.4` discovered, but great definitions are often the residue of some kind of insight.
`  171.0` See, these two specific terms are really not hard to define in the sense of
`  174.7` laying down a formula for you, but doing so too early would spoil a good story.
`  178.9` It is much more fun to see how you are inexorably drawn to
`  182.2` them by asking about the limits of compressing language.
`  185.5` And what I want you to notice by the end here is how we can't
`  188.9` really answer this question, or at least Shannon couldn't,
`  192.2` without necessarily engaging with some notion of intelligence.
`  199.0` We will get to modelling language, which is wonderfully complicated,
`  202.6` but it helps to warm up with a simpler example containing the
`  205.9` same essential ideas needed for our path of rediscovery.

## [210s] The warmup example

`  209.7` Imagine you have a robot that we have sent to a faraway moon,
`  212.8` whose job is to wander the surface and collect data.
`  216.0` From here on Earth, we send it instructions for how to move
`  218.7` that are going to be limited to four very simple possibilities.
`  222.2` Move up, down, left, or right, each one with a fixed step size.
`  227.4` The nuance will be that these instructions are not uniformly distributed.
`  232.0` Half of everything we send is up, one fourth of the instructions are down,
`  236.4` one eighth are left, and the other eighth are right.
`  240.1` It's a little contrived, it's meant to be a simple example,
`  243.0` and in that spirit of simplicity, we're also going to assume that every instruction
`  247.0` is independent.
`  248.3` They are sampled from this distribution regardless of the preceding context.
`  252.7` When we send data to this bot far away, we're doing it as a stream of bits,
`  256.8` ones and zeros, and it's very slow and costly to do that, so the natural question,
`  261.2` the warm-up puzzle for you today, is to ask what is the most efficient
`  265.1` possible way to encode these instructions as a stream of bits.
`  269.2` And here, we might imagine three students who each attempt an answer,
`  273.1` one who's straightforward, one who is clever, and one who is very theoretical.
`  278.1` The straightforward student immediately raises their hand and says,
`  281.2` well, for each of these four instructions, we could just use two bits.
`  285.0` Maybe 00 encodes up, 01 encodes down, 10 encodes left, and 11 encodes right.
`  292.6` On the receiving end, this makes it very easy for the robot to decode.
`  295.9` It simply breaks up the bitstream into chunks of two,
`  298.7` and translates each chunk into the appropriate instruction.
`  302.8` Now, the clever student points out, well, that does nothing to take advantage
`  306.6` of the fact that up comes up way more frequently than left or right.
`  310.5` They propose a method where we use a different number of bits for each instruction.
`  315.0` I'll explain it in just a second, but I do want to call out the fact that
`  318.4` as soon as you let different instructions get different numbers of bits,
`  321.9` it's certainly not obvious that the robot is going to know how to decode it.
`  325.6` After all, it needs to somehow know where to draw the dividing lines.
`  330.7` Now, being very clever, the second student has thought that through,
`  333.8` but it's easiest to explain if I just kind of lay it all out.
`  337.2` What they suggest is letting the single bit 0 represent up,
`  341.3` letting the two bits 10 represent down, using 110 for left and 111 for right.
`  347.7` You can calculate the average number of bits per instruction
`  350.6` that this would require with a simple weighted sum.
`  353.1` Half the time, only one bit is used, a quarter of the time,
`  356.4` two bits are needed, and the remaining times, you need three bits.
`  360.8` When you add this all up, as a weighted sum, you get 1.75 bits per instruction,
`  364.9` which is indeed better than the more naive approach of a flat two bits per instruction.
`  370.1` The second student is spending more bits on those last two instructions,
`  373.6` but because they come up so much less frequently,
`  376.0` this is more than made up for by using only one bit for that most common instruction.
`  380.2` And you can see this efficiency bear out empirically too.
`  384.1` This right here is a set of instructions sampled from that distribution.
`  388.2` You'll notice lots of ups, about half as many downs, and even fewer lefts and rights.
`  394.0` When you turn each symbol into the appropriate bit string following this encoding,
`  398.2` the resulting sequence of bits is indeed shorter than what the naive method gave.
`  403.3` But I hear some of you asking, how does the robot know how to decode this?
`  407.1` Can we be sure that there's an unambiguous way to draw the dividing lines?
`  411.5` In the lingo of encodings, each of these four bit strings
`  414.1` used to encode the instructions is called a code word.
`  417.1` And as we step through things here, see if you can figure out what rule the clever
`  420.7` student was following to make sure that their code words don't conflict with each other.
`  425.5` And really, you just need to look at an example bit
`  427.9` stream from the robot's perspective and think it through.
`  431.3` Let's say that that very first bit that it receives is a 1.
`  433.9` So far, this could be encoding any of the last three instructions, down, left, or right.
`  439.5` If what follows is a 0, then it can only be down.
`  443.4` There is no other possibility.
`  445.0` So the robot can register that as a complete instruction.
`  448.1` From there, starting fresh, if what follows is a 0,
`  450.9` that must be encoding up, since there is no other possibility.
`  454.7` Nothing else starts with a 0.
`  456.6` After that, if they see a 1, this is so far ambiguous,
`  459.3` it's the prefix for any of the last three code words.
`  462.0` If the next bit is another 1, it remains ambiguous, it's the prefix of the last two.
`  467.4` But that following 0 then makes clear these three bits must have been encoding left.
`  472.9` In short, all the robot has to do is read in the next sequence
`  476.1` of bits until the moment that it forms a complete code word,
`  479.2` at which point it can register it as a complete instruction.
`  484.0` If you step back and think about it, the key constraint for this
`  487.6` all to work is that no code word can be a prefix of another one.
`  491.3` For example, let's say you tried to introduce some
`  494.2` fifth instruction that had the code word 100.
`  497.6` That would cause conflicts, because after reading 10,
`  500.2` it's not clear whether that's supposed to be down,
`  502.8` or if it's supposed to be the start of this new fifth instruction.
`  507.1` When you avoid this kind of conflict, an encoding method like this has a special name.
`  511.5` It's known in the business as a prefix-free code, or what is confusingly synonymous,
`  516.1` it's actually more commonly known as a prefix code.
`  518.9` And there's a really nice way to visualize choosing prefix-free codes
`  522.9` with a certain diagram that represents every possible binary string.
`  527.5` This diagram also has some helpful parallels with
`  529.9` how I want to show entropy in just a few minutes.
`  532.7` It's probably decently intuitive what's going on if you just pause
`  535.5` and stare at it for a bit, but I'll call out the important features.
`  539.5` Each layer shows every bit string of a given length,
`  542.5` and you'll notice everything that starts with a 0 lives on the left half
`  546.6` of this diagram, and everything that starts with a 1 lives on the right
`  550.8` half of the diagram.
`  552.5` And that same idea continues recursively as you go up.
`  556.2` So everything starting with 00 is above this quarter of the diagram,
`  560.3` everything starting with 01 is above this quarter of the diagram, and so on.
`  565.5` In particular, the key property is that every binary string in
`  569.2` this diagram is a prefix for everything that sits above it.
`  572.8` So when our clever student chose to allocate a single bit 0 to
`  576.7` represent the instruction up, they were effectively consuming half
`  580.9` of the space of all possible code words by doing so,
`  584.3` since everything starting with a 0 is now prohibited based on this prefix-free property.
`  590.7` Similarly, allocating one 0 to down eats up another fourth of this space,
`  594.9` and the remaining two instructions each eat up an eighth of the space.
`  599.3` You can just see how nothing is left over.
`  602.0` And at this point, I'm guessing that there's some bell kind of resonating in your mind,
`  607.1` given that these proportions are all exactly the same as the
`  610.7` probability for each instruction coming up.
`  613.7` And in fact, that tickling sensation of a relationship between data size
`  618.0` and probabilities is exactly the founding insight for information theory.
`  623.2` When you stare at this pleasing alignment, it might suggest that the
`  627.0` clever student's solution is not just better, maybe it's somehow perfect.
`  632.1` But at the moment, that feels like a bold claim to make.
`  634.6` How could you know that there's not some ultra-clever method that does
`  638.1` something fancy with really long sequences of instructions that somehow
`  641.7` makes it so the average bits per instruction gets even lower than this?

## [646s] What perfect compression looks like

`  646.2` This takes us to the third student, Head in the Clouds,
`  648.8` who has not really been thinking about actual codes that they can implement.
`  652.4` They have been pondering what properties a perfect, optimally efficient code would have.
`  658.7` They have this really clever idea, which is to argue that random noise
`  662.4` should be incompressible, and therefore, a perfect compression algorithm
`  666.3` should produce a bitstream that's indistinguishable from random noise.
`  670.7` What's neat is, even though that sounds kind of simple,
`  673.3` this can actually lead you to reinventing the idea of Shannon entropy.
`  677.4` Now when I say random noise, what I mean is that each bit is a 1 or a 0,
`  681.4` with 50% probability, and all of the bits act independent from one another.
`  686.1` It's not hard to show that our second student's
`  688.3` encoding for the robot genuinely follows this rule.
`  691.2` If you think about it, there's a 50% chance that the message starts with the
`  695.7` instruction up, so that first bit has a 50% chance of being a 0, otherwise it's a 1.
`  701.0` And then if it is a 1, there's a 50% chance that the instruction is down,
`  705.4` meaning the next bit is 0, otherwise it's a 1.
`  708.1` And so on.
`  709.9` Each new bit really does act like an independent coin flip, so to the receiver,
`  714.2` that compressed bitstream really is indistinguishable from random noise.
`  719.3` But why am I saying that random noise is incompressible?
`  722.7` Well, for that, let's really focus on things from the receiver's perspective.
`  726.3` And here, instead of thinking instruction by instruction,
`  729.1` it helps to zoom out and frame our discussion in terms of
`  732.0` entire messages and what the encoding for full messages looks like.
`  735.3` When that receiver sees a string of n bits representing some compressed message,
`  739.9` this is one out of 2 to the n possible messages they could
`  743.3` have received that would have the same size.
`  746.2` And then critically, because we're assuming this looks like random noise,
`  749.7` all 2 to the n of those messages must be equally likely.
`  753.1` Now to be clear, we're not just talking about the robot example anymore.
`  756.6` Our theoretical head-in-the-cloud student really wants to make an argument for
`  760.6` what perfect compression looks like for any data type,
`  763.4` like maybe we're compressing language or compressing images,
`  766.5` and they want an argument that works regardless of the details of what specific
`  770.6` compression algorithm you're using.
`  773.1` A loose intuition in your head is that maybe among all of the messages that
`  776.9` compress down to n bits, some of them would contain a larger amount of predictable data,
`  781.6` while others would have started as a smaller amount of unpredictable data.
`  785.8` But the key point is that if the compressed bitstream really does look like random noise,
`  790.7` meaning all of the bitstrings of size n are equally likely,
`  794.0` it must be the case that all the underlying messages being compressed were
`  798.2` equally likely to arise, and even more specifically with probability 1 over 2 to the n.
`  803.6` So again, why am I claiming that this is incompressible?
`  807.5` Well, let's pull up that same diagram, representing
`  810.2` the space of all possible binary strings.
`  813.0` In this case, we can think of all the encodings for our 2 to the n equally
`  817.5` likely messages as being the bitstrings on one layer of this diagram.
`  822.6` If you tried to define an alternate scheme, where you tried to become more
`  826.6` efficient by making one of these messages use fewer bits,
`  829.7` it would move lower on the diagram, which means it then overlaps with some
`  833.8` other message, so you would have to put that other message somewhere else
`  837.8` in this diagram.
`  839.2` At minimum, that means it's sharing a space with yet a third message,
`  842.8` and those last two have to kind of get bumped up one layer,
`  845.8` requiring that extra bit for each of them to disambiguate.
`  849.4` So saving one bit over here costs you two bits elsewhere.
`  853.4` You're basically pushing down a bump on the rug,
`  855.6` only to see it pop up even worse in another spot.
`  858.9` In general, any message encoded with a string lower on this diagram is going to be eating
`  863.6` up more than its fair share of the space, which forces multiple other messages to occupy
`  868.3` a smaller region, bumping them higher up, meaning they're encoded less efficiently.
`  872.7` I'm going to guess that it's decently intuitive for everyone watching that
`  876.1` the most efficient scheme here for equally likely messages is to give them
`  879.6` all the same number of bits, but I do think the diagram gives a more
`  882.9` concrete way to see why you end up with unfavorable trade-offs otherwise.

## [887s] Defining information

`  887.3` Once you have this idea that perfect compression looks like random noise,
`  890.8` this is exactly the kind of thing I was referencing in the intro,
`  893.8` about how insights can lead you to definitions.
`  896.9` Notice how what we're basically saying is that a message that uses n bits in a
`  901.7` perfect scheme must have a probability of 1 over 2 to the n, or 2 to the negative n.
`  907.6` If you take the log base 2 of both sides here and then negate,
`  911.1` this is equivalent to saying that the number of bits allocated to a message,
`  915.4` assuming perfect compression, is negative log base 2 of p,
`  918.6` where p is the probability of occurring.
`  922.2` This negative log expression is the fundamental formula for all of information theory.
`  927.9` Everything up to this point is me trying to make this value feel like
`  931.5` something you are inevitably drawn to by asking about perfect compression,
`  935.4` rather than it feeling like some arbitrary definition that we start with.
`  939.7` Some students do find this negative log takes a little getting used to.
`  943.2` You know, it looks like it should be a negative value before you think about the fraction
`  947.3` in the middle, but really the intuitive way to read it is that it's asking how many
`  951.1` times do you chop your space of possibilities in half to get to a certain quantity.
`  955.5` Here, let me pull up some axes and show you the graph of negative log of p.
`  960.0` I've also seen some authors default to writing this as the log of 1 over p,
`  964.1` which maybe you find more intuitive.
`  966.7` You could also think of it as the log base 1 half of p,
`  969.2` which I've never really seen anyone lean into,
`  971.3` but personally I would be quite partial to that as a convention.
`  974.9` Now, however you write it, what Shannon realized is that this is a very
`  978.8` useful way to think about the information that a message contains even
`  982.6` when literal perfect compression is not possible and p is no longer a clean power of 2,
`  987.4` which would mean that the output here is some fractional amount.
`  991.3` In fact, he defined this expression to be the information of an event.
`  996.2` The image I sometimes have in my head is to picture the probability of an event
` 1000.5` with a little pie chart, and the information is this bar above it that gets
` 1004.6` kind of pumped up to be taller as the probability is squeezed closer to zero.
` 1009.2` That is, unlikely messages contain a lot of information,
` 1012.7` and the bar is relaxed to get shorter as the probability approaches 100%.
` 1017.9` Highly expected messages contain very low information.
` 1021.9` I want to be clear that there is content to this definition.
` 1025.1` It's more than just rescaling probabilities, as if converting to an alternate unit system.
` 1030.3` You've already seen the core idea.
` 1032.0` In a perfect compression scheme, the number of bits allocated
` 1035.5` to a full message precisely equals this information content.
` 1039.5` Now, of course, perfect compression is not always possible.
` 1042.1` Your probability's messages are likely not perfect powers of 2.
` 1046.1` So the more general way you would frame this is to say that the
` 1049.1` information of a message gives you a lower bound on how much it can be compressed,
` 1053.0` at least when you average overall possible messages.
` 1055.8` It's perfectly possible to overfit a compression algorithm to one specific case.

## [1061s] Information of language

` 1060.6` And to really wrap your mind around information and fractional bits,
` 1063.7` we need to step up our game beyond that warm-up example.
` 1067.0` See, with the robot, the probabilities were overly clean.
` 1069.7` They were all perfect powers of 2, so that the information
` 1072.6` per symbol could precisely match a whole number of bits.
` 1075.8` But Shannon was very interested in this question of limits on compression
` 1079.8` for much more realistic and complicated cases, like natural language.
` 1084.1` For example, here I'll pull up the probabilities for each new letter in an
` 1088.1` example phrase, at least as determined by a little GPT that I'm running locally.
` 1093.1` And, by the way, if the probabilities provided by a model feel like those might be
` 1097.0` distinct from the probabilities of actual language,
` 1099.4` you would be right to raise an eyebrow.
` 1101.7` Hold on to that thought.
` 1102.8` It becomes very relevant later.
` 1104.9` One key difference with language is how heavily dependent on context everything is.
` 1109.9` The probability distribution for each new letter you see is highly,
` 1113.5` highly contingent on everything that came before it.
` 1116.7` The other big difference is that all of these probabilities
` 1119.5` are obviously not going to be clean, perfect powers of 2.
` 1122.2` So if you compute the Shannon information of each one of these,
` 1125.5` meaning you take the negative log base 2, all the numbers that you see are
` 1129.6` fractional amounts.
` 1131.2` And again, giving a vague interpretation of what these mean is really not hard.
` 1135.5` Information content is low for very predictable letters,
` 1138.8` and it's high for very unpredictable letters.
` 1141.8` But all of you watching this are smart enough to demand a more exact interpretation,
` 1146.3` one that justifies why these values deserve to be given the units of bits.
` 1150.3` I mean, it's not like there's going to be some perfect encoding where this
` 1154.8` letter i has a code word that is somehow 4.19 bits,
` 1158.0` or where this highly predictable o is somehow encoded with just a narrow sliver of a bit.
` 1164.0` The real meaning is related to encoding entire messages
` 1167.0` and coming up with a bound on their compression.
` 1170.5` The probability for a full phrase, like the one I'm showing here,
` 1174.0` looks like multiplying the probabilities for each successive new letter, where again,
` 1178.5` I'll emphasize that these successive letters' probabilities are conditioned on what
` 1183.0` came before.
` 1184.2` This is essentially the chain rule from probability.
` 1187.0` I want you to notice how nicely this plays with a logarithm.
` 1190.4` If you ask for the information of that full message, taking this negative log expression,
` 1195.5` because logarithms turn multiplication into addition,
` 1198.6` this breaks up really nicely as the sum of the information for each individual letter.
` 1204.0` In the final part of this trilogy, I'm going to walk you
` 1206.6` through a very specific compression algorithm that would
` 1209.3` actually compress this text to within one or two bits of this value.
` 1213.0` It's no longer as simple as mapping each character to a predefined code word,
` 1217.2` but you nevertheless get this very direct sense of thinking about adding up the
` 1221.6` fractional information content of each letter to determine the length of the final
` 1226.1` encoding that you use.
` 1228.0` So that's the key idea.
` 1229.1` Even if, by the time you need to relate this to actual data sizes,
` 1232.5` things will get rounded off to the nearest whole number,
` 1235.4` what Shannon realized is just how useful it is to work at this higher layer of
` 1239.5` abstraction, where all your information is allowed to freely be continuous and
` 1243.5` information of successive events really nicely adds together.
` 1248.0` Still, if you step back and imagine yourself very seriously assessing
` 1251.6` the fundamental compressibility of language, all of this hinges on the
` 1255.2` question of how you know the probabilities for each successive letter.
` 1259.5` Here, for all these animations, I've been illustrating things using a language model,
` 1263.6` but for one thing, that doesn't necessarily feel the same as the true
` 1267.0` probabilities underlying language, and for another,
` 1269.6` it's not even clear what we would mean by the true probabilities of language.
` 1274.2` So here, I actually think it's most enlightening to take a step
` 1277.3` back in time and see how Shannon himself thought about all of
` 1280.4` this long before language models or modern data analysis.
` 1283.9` Some of his earliest experiments on the information of language involved
` 1287.6` looking at specific short sequences of characters,
` 1290.3` what you often hear referred to as n-grams, and then tracking the statistics
` 1294.3` of what tended to follow.
` 1296.2` So, for example, if you scan through a few books,
` 1298.5` and you notice every single time the two letters th come up and you
` 1301.7` record what letters tend to follow, you could build up a table of
` 1304.8` those letters and let those statistics represent a sample for the
` 1307.9` probabilities you care about.
` 1309.9` Now, the problem is that this just completely breaks down for longer strings of letters,
` 1314.0` most notably, any string of text that never shows up in all
` 1316.8` of the books that you're analyzing.
` 1318.4` Nevertheless, it's perfectly reasonable to talk
` 1321.1` about what's expected to follow such a longer string.
` 1324.6` In fact, if anything, it's more important to talk about those cases,
` 1327.9` since longer context windows are when things are at their most predictable,
` 1331.6` and that's where you stand to get the most compression due to that predictability.
` 1336.6` So instead of using raw statistics, a little bit later,
` 1339.6` Shannon analyzed a different model of the English language that he had available to him,
` 1344.5` his wife Betty.
` 1345.4` As the story goes, Shannon pulled out a book and
` 1348.2` began asking Betty to guess each next letter.
` 1351.6` Shannon would then transcribe her guesses letter by letter.
` 1354.5` Every time she guessed incorrectly, he wrote down the correct letter,
` 1358.1` and then whenever she guessed correctly, he would just replace it with a dash.
` 1363.0` The idea was that this transcribed version he was creating has fewer
` 1366.5` actual letters than the original, but his point was that it contained
` 1370.0` the same amount of information, at least in the following sense.
` 1373.3` If he could somehow obtain an exact replica of his wife and conduct the
` 1377.4` guessing game again, he would only need to supply her with this reduced text.
` 1382.2` These letters by themselves would provide just the right prompting
` 1385.6` for his duplicate wife to exactly reproduce the original.
` 1389.1` Of course, in practice, a person wouldn't necessarily guess the same way twice,
` 1393.3` and while this qualitatively conveyed the idea of predictability allowing
` 1397.2` for compression, it wasn't yet a measurement of information.
` 1400.5` A bit later still, in his 1950 paper, Prediction and Entropy of Printed English,
` 1405.0` Shannon updated the experimental design to get a more robust read on this
` 1409.1` slippery question of the average information content in English.
` 1413.3` This time interviewing more people, instead of just logging whether
` 1416.7` each guess was right or wrong, Shannon recorded how many guesses were
` 1420.2` necessary for a human guesser to come up with the correct next letter.
` 1424.7` And then separately, he had this whole method for associating
` 1427.8` the number of guesses required with an implicit probability
` 1430.9` that a person would have been assigning to the true next letter.
` 1434.7` The details of that are a little bit in the weeds,
` 1437.2` but the broader point I want to make is how, in analyzing language,
` 1440.5` he wasn't just doing pure data analysis looking through books.
` 1444.1` He was trying to probe at an underlying model of language, namely the interviewee's brain.
` 1450.3` These brains that he could talk to were effectively treated as black boxes,
` 1454.5` ones with a sophisticated and yet indescribable understanding of
` 1458.1` language and an ability to predict characters based on the context.
` 1462.7` Now these days, in the 2020s, we have gone from merely
` 1465.5` interrogating black boxes that process language to designing them.

## [1470s] Defining Entropy

` 1469.9` The reason that you and I are here, revisiting the roots of information theory
` 1474.0` and this study of how compressible language is,
` 1476.6` is because of how much of the math in modern machine learning leverages the
` 1480.7` formulas that emerged in this field.
` 1483.2` Aside from the definition of information itself,
` 1485.8` there are three more key expressions that I want you to feel like you could
` 1489.9` have rediscovered, not just because rediscovery makes them more memorable,
` 1494.0` but because seeing how they naturally arise from studying compression gives a
` 1498.3` more solid ground from which you can assess that thought-provoking interplay
` 1502.5` between compression and intelligence.
` 1505.1` You already have everything you need to reinvent the first of these, which is entropy.
` 1510.1` Imagine you have any signal that can be thought of as a sequence of symbols,
` 1513.9` whether that's the four robot instructions, the English language,
` 1517.1` or really anything else you dream up.
` 1519.5` Entropy asks about the average amount of information for each symbol,
` 1523.1` and then based on everything we've been discussing,
` 1525.8` where perfect compression looks like random noise, and how, in that case,
` 1529.6` the number of bits used for a message is the same as the information content
` 1533.6` of that message, which again breaks down really nicely as the sum of the
` 1537.4` information of all the symbols.
` 1539.4` This question of measuring the average information per
` 1542.1` symbol is basically asking about the limit of compression.
` 1545.6` It would give you a lower bound on how efficiently a given signal could be compressed.
` 1551.0` And you and I already calculated this in one setting,
` 1553.7` when we took that weighted sum to find the average bits per instruction for the
` 1557.8` perfect encoding of the robot case.
` 1560.1` Basically, because that encoding was perfect, each symbol's code
` 1563.3` word length is exactly the same as its information content.
` 1566.9` So, effectively, we're calculating the average information per symbol.
` 1570.3` To generalize this, here's how that looks.
` 1573.1` For any given probability distribution, characterizing whatever symbols your
` 1577.7` messages are made out of, the average information per symbol should look like
` 1582.5` adding up p times the negative log of p for each probability p in that distribution.
` 1588.5` And take a moment to notice how we're visualizing this expression.
` 1592.0` Throughout the video, we've been picturing probability
` 1595.0` distributions with stacked horizontal bars, where each bar's
` 1598.4` width is equal to its probability, so altogether they add up to be 1.
` 1603.2` Now, above each one of those, I've put a rectangle whose height is locked to be
` 1608.0` the corresponding information value, the negative log base 2 of that probability.
` 1613.8` So the weighted sum up top, the average information per symbol,
` 1617.1` can be thought of as the total area of all these rectangles together.
` 1621.8` This is not yet fully general.
` 1623.4` It only describes the compression limit in cases where
` 1626.3` every new symbol follows some identical distribution.
` 1629.7` That's true in the robot case, but it's not true in English, for example.
` 1633.6` Nevertheless, it's important enough to deserve a name.
` 1636.7` And there's a fun story about how John von Neumann supposedly told Shannon that he should
` 1641.5` call this expression entropy, since, for one thing,
` 1644.3` it resembles an expression already used for the idea of entropy in statistical
` 1648.6` mechanics, and for another, quote, nobody knows what entropy really is,
` 1652.5` so in an argument, you'll always have the advantage.
` 1655.3` I looked into it, it's probably apocryphal, but
` 1657.7` there seems to be a grain of truth to this.
` 1660.6` Now, whatever the true story is, Shannon did call this quantity entropy,
` 1664.6` and he denoted it with the letter h.
` 1667.2` And it's fun to take a moment to play around with
` 1669.1` this graphic to build a little intuition.
` 1671.5` The more evenly distributed a probability distribution, the higher the total entropy,
` 1676.3` whereas if we squish things to become very uneven,
` 1679.3` maybe with one event dominating the probability space,
` 1682.4` this would have a very low entropy, since that one overwhelmingly probable event
` 1687.1` carries correspondingly little information.
` 1690.3` And then also, if you divide up the probability space even more,
` 1693.9` meaning it's distributed over more total possible symbols,
` 1697.1` each one has more information, so the total entropy is higher.
` 1701.1` And once more, it's fun to kind of slosh everything around,
` 1704.5` where a very skewed distribution gives lower total entropy,
` 1708.0` whereas a more even spread gives us higher entropy.
` 1711.0` The vague qualitative intuition here is that entropy measures the amount of
` 1715.4` uncertainty in a distribution, but the more precise understanding,
` 1719.3` justifying why it deserves to be given in units of bits,
` 1722.6` is that it describes the minimum number of bits per symbol necessary to encode
` 1727.2` a message following this distribution.
` 1730.2` That statement, and everything we just covered,
` 1732.7` is more or less the content of a core theorem in Shannon's
` 1736.0` 1948 paper that kicked off information theory, the noiseless coding theorem.
` 1740.2` It states that no encoding can ever be more efficient than this limit,
` 1744.1` and even more strongly, he showed that it's always possible to get arbitrarily close
` 1748.7` to this limit.
` 1751.3` Now like I said, this expression only applies in cases where every symbol follows the
` 1755.6` same distribution, but Shannon was of course keenly interested in a more general
` 1759.7` setting, where the probabilities for each new symbol don't necessarily follow the same
` 1764.0` distribution.
` 1764.7` In particular, he spent a ton of time contemplating
` 1767.6` the compressibility of natural language.
` 1770.5` This requires a more general notion of entropy,
` 1772.8` something known as the entropy rate for a stochastic process.
` 1776.4` But it's the same basic question.
` 1778.2` What is the average information per symbol, except in
` 1781.2` this case we're now averaging over all possible messages.
` 1785.0` This is almost never a clean calculation that you can perform
` 1787.9` with some clean visual like the one we were just playing with.
` 1790.9` After all, what formula describes the probability distribution for language?
` 1796.2` So if you hear reference to the entropy of language,
` 1799.1` this is well beyond what any exact calculation can give you,
` 1802.5` hence why Shannon turned to estimates based on observation.
` 1806.3` And again, his methodology was not just data analysis.
` 1810.0` It's not some function that you can perform on a corpus of text.
` 1813.5` In order to get a satisfying estimate on compressibility,
` 1816.8` he found himself inevitably needing to probe at intelligent models of language.
` 1822.0` When his interviewees had at least 100 preceding letters of context,
` 1825.6` he estimated the entropy of English to be about one bit per character.
` 1829.9` This is a pretty wild number when you think about it,
` 1832.5` because it suggests that English could be compressed down to just a single yes or
` 1836.6` no answer for each character.
` 1839.1` Wild as that sounds, in the third part here, I will show you that algorithm I've
` 1842.8` referenced, where if you're allowed to use a high-quality language model for
` 1846.5` encoding and decoding, you can get surprisingly close to this limit in practice.
` 1851.1` Before then, it helps to understand a variation on entropy, known as cross-entropy,
` 1855.9` asking both how and why it's used in training large language models.
` 1860.4` If you want to learn that, as well as a few fun related ideas like how
` 1864.2` large models are distilled into smaller ones,
` 1866.7` and why on earth GZIP can recover the structure between distinct languages,
` 1870.8` come join me in part 2.

## [1874s] 3b1b Talent

` 1874.3` Regular viewers will know that my new experiment for this
` 1877.5` year is to have a virtual career fair, a page at 3b1b.co.
` 1881.1` talent, where this audience can explore aligned career opportunities.
` 1885.2` The meaningful update is just how much more content there is now,
` 1888.3` mainly in the form of featured interviews between me and the relevant teams.
` 1892.7` Here's my thinking.
` 1893.6` I feel like when you're assessing potential jobs,
` 1895.9` it's almost impossible to get a true sense of what it's like to work at a place just by
` 1900.1` poking around online, and you learn orders of magnitude more if you have a chance to sit
` 1904.4` down for lunch with a couple team members.
` 1906.7` My hope is to give you the vicarious version of that.
` 1910.0` So, if you're curious what I mean when I say these are all thoughtful and curious teams,
` 1913.9` go take a moment to explore.
` 1915.3` I really think you'll enjoy it.