# But what is cross-entropy? | Compression is Intelligence Part 2

Длительность 2031 с. Реплик 576. Чаптеров 10.


## [0s] Language trees and zipping

`    0.0` There's a kind of wild paper from 2002 called Language Trees and Zipping,
`    4.1` which shows how you can find structure between languages just by using very general file
`    9.0` compression.
`   10.5` For example, let's say I give you a bunch of text documents in many different languages,
`   14.6` and your goal is to automatically cluster them by language.
`   18.0` And actually, you can aim even higher than that.
`   20.1` Suppose you also want to recover which languages are most closely related to each
`   24.2` other in a way that lets you rediscover the tree of shared lineage between them,
`   28.3` and all you can do is write a function that processes the text in each one.
`   32.3` There's no pre-baked knowledge of linguistics.
`   34.9` Now keep in mind, this is almost a quarter century ago,
`   37.6` so nothing like modern language models is available.
`   40.6` What's crazy is how the authors showed that you can do this just by using gzip,
`   44.4` basically the same operation that you might use on your computer to make files a bit
`   48.4` smaller.
`   49.4` Here's the basic idea.
`   50.8` Given two documents, A and B, append a small snippet of B to the end of A,
`   55.4` and compress the result.
`   57.0` Now compare that file size to what you get just by compressing A on its own.
`   63.1` One way to think about this difference is it's telling you how well a little
`   67.0` snippet of B gets compressed when the compressor is mostly optimized for A.
`   71.3` You'd expect that result to be small when the linguistic patterns of B
`   74.9` are similar to those in A, but larger when B is more different from A.
`   79.3` The authors used this general idea to define a specific metric for how far
`   83.4` away two documents are, based exclusively on how well they compress together.
`   88.2` And then, evidently, this co-compression-based distance
`   91.2` was enough to recover the tree of language lineage.
`   94.5` And it doesn't stop there.
`   95.5` The same trick can be used for other natural language tasks,
`   98.6` like identifying who authored a given document.
`  102.6` What I like about this paper is what a pure example it is of when the theory and
`  106.6` the engineering behind compression can be surprisingly useful to tasks which
`  110.5` would seem to fall in the domain of machine learning and artificial intelligence.
`  114.6` The specific concept underlying this example is something known as cross-entropy.
`  119.2` And what's interesting is that cross-entropy is also a very core part
`  122.6` of how modern language models are trained, which gives a whisper of
`  126.0` an unexpected connection between that training and compression.
`  129.8` Most of what I want to do with this video is provide
`  132.1` a lesson that goes back to the basics.
`  134.2` We're going to spend the first half on the fundamentals of what cross-entropy is,
`  137.9` how it naturally arises in the study of compression, and how you can visualize it.
`  141.7` Then after that, we're going to go through the fundamentals
`  144.4` on pre-training and distilling language models.
`  146.9` And what's interesting is how, in that second half,
`  149.2` the way that cross-entropy arises initially looks completely different.
`  152.6` It seems unrelated to compression.
`  154.7` But whenever you see the same formula pop up in two separate contexts,
`  158.1` it's math's way of kind of winking at you and hinting at a connection.
`  162.2` So at the end, armed with an understanding of where cross-entropy really comes from,
`  166.1` combined with an understanding of pre-training,
`  168.3` I want to show you how you can reframe the way you think about training
`  171.6` large language models to not be about next token prediction,
`  174.4` but instead to be about compression.

## [182s] Recap optimal codes

`  182.2` It's easiest to motivate cross-entropy in the
`  184.8` context of encoding messages into sequences of bits.
`  188.1` This is a topic we began discussing in part one,
`  190.5` where the framing is that we treat messages as sequences of symbols,
`  193.9` something like characters of text, and if you treat each new symbol like it's being
`  198.1` sampled from some probability distribution, those probabilities tell you something
`  202.2` about the fundamental limits on compression.
`  205.1` Now, the case of natural language is incredibly complicated,
`  207.9` those distributions would be very difficult to describe,
`  210.5` so we centered a lot of our discussion on a very simplified toy example.
`  214.3` And I want to pick up from that thread here, since
`  216.3` that example also helps motivate cross-entropy.
`  218.7` The setup was that we're sending sequences of
`  221.0` four possible instructions to some faraway robot.
`  223.6` Move up, down, left, or right, and each symbol we send is sampled from a distribution
`  228.5` that gives a 50% chance to sending the instruction up, a 1 in 4 chance of sending down,
`  233.5` and a 1 in 8 chance for each of the remaining symbols left and right.
`  237.8` It's as if we want the robot to do some specific biased random walk.
`  241.8` One of the conclusions we came to in part one was how the best possible
`  246.1` encoding here turns the symbol up into just a single bit,
`  249.6` turns that symbol down into two bits, and turns left and right each into three bits.
`  255.1` The whole point of this toy example is that it's a concrete illustration
`  258.9` of a much more general fact, which is that for an optimal code,
`  262.4` the number of bits that you allocate to a given symbol looks like
`  265.9` the negative log base 2 of the probability for that symbol showing up.
`  270.1` This negative log expression takes a little getting used to.
`  273.1` I mentioned how I kind of wish that history had unfolded in such a way that we
`  276.8` call it the log base 1 half of the probability,
`  279.0` since it's really just asking how many times do you chop things in half to
`  282.5` get down to a certain amount.
`  284.7` Claude Shannon defined this expression to be the information content of an event.
`  289.7` Now of course usually the numbers aren't so clean,
`  292.1` so this information value is typically not a whole number,
`  295.0` meaning your optimal codes can't look so simple as associating a symbol
`  298.6` with some specific string of bits.
`  300.7` The more general way to think about it is that to encode a full message,
`  304.5` the information content of the full message looks like the sum of the
`  308.3` information contents of all the individual symbols,
`  311.0` and the number of bits in an optimal encoding of the message is approximately
`  315.2` that full information content.
`  317.2` So fractional information really does have a very real meaning here.

## [321s] Defining cross-entropy

`  321.0` Now for part 2, imagine your space agency has decided to change the plan,
`  325.1` effectively rotating things to encourage an overall more rightward journey,
`  329.3` where from now on the symbols up and down each have a 1 in 8 chance,
`  333.2` the symbol left has a 1 in 4 chance, and right is sampled fully half of the time.
`  338.3` Supposing all of your encoding and decoding systems are hard-coded
`  341.9` to use the previous encoding scheme, optimized for the old distribution,
`  345.9` this is obviously now inefficient, but how inefficient exactly?
`  350.3` And this is not that hard to calculate.
`  352.6` Now the single bit instruction for up comes up only one eighth of the time,
`  357.1` the two bits for down also come up only one eighth of the time,
`  361.0` and the other two instructions each require three bits,
`  364.4` which together happens 75% of the time.
`  367.6` Adding this up as a weighted sum, you get an average of 2.625 bits per message.
`  373.8` You would say that this number represents the cross entropy
`  376.9` of the original distribution relative to the new one.
`  380.1` If you've optimized a compression scheme around one context,
`  383.6` how does it perform in another context?
`  386.8` Even just as I've stated things so far, perhaps this already rings a few bells
`  390.4` in your mind as you think back to that zipping and language tree example.
`  394.4` Before spelling that out, it is worth our time to take a few
`  397.0` minutes generalizing this and packaging it into a couple formulas.
`  400.6` Let's label all the probabilities from our new distribution with the letter P,
`  404.5` and then all of those from the original distribution with the letter Q.
`  408.6` And instead of limiting ourselves to four robot instructions,
`  411.7` let's consider the general case of messages that look like any sequence of symbols.
`  415.9` Those symbols could be the four robot instructions,
`  418.2` they could be the characters of English text,
`  420.3` or they could be anything else you dream up.
`  422.9` An encoding optimized for this first distribution, Q,
`  426.4` allocates negative log base 2 of Q sub i bits to each symbol.
`  431.1` So the average bits used per instruction looks like this weighted sum.
`  435.7` Basically, you go through each symbol, and for each one you take the
`  439.1` proportion of times that it comes up, which is its probability,
`  442.3` multiplied by the information content, the negative log base 2, of its probability.
`  447.4` This sum was the other key term we had in the last lesson,
`  450.7` the entropy of Q, and we visualized it as the area of this diagram.
`  455.2` Each bar represents one part of the weighted sum.
`  458.0` Its width is Q, and its height is the negative log base 2 of Q.
`  463.3` But if the distribution that arises in practice is something else, P,
`  467.4` and we keep using an encoding optimized for Q,
`  470.1` then the average number of bits used per instruction would still look like a weighted
`  475.2` sum, but now the weights are these new probabilities, P.
`  479.8` So this general expression is, by definition, the cross
`  483.6` entropy of the distribution Q relative to the distribution P.
`  488.7` The specific notation that you'll see out in the wild is a little bit of a mess,
`  492.0` there's a lot of different conventions.
`  494.0` For you and me, we'll just think about the sum itself, visualized with this diagram,
`  499.3` where the width of each bar is P sub i, while the height is the negative log base 2 of Q
`  505.0` sub i.

## [506s] Intuition and examples

`  506.3` With any new formula, it helps to build some intuition with very simple examples.
`  510.4` So in this case, instead of having distributions with many possible events,
`  514.5` consider a distribution with only two events.
`  517.4` And let's say Q is an even distribution that assigns a 50% chance to each event,
`  522.9` while P is more skewed, assigning 90% to one and 10% to the other.
`  527.8` This would mean, from Q's perspective, each event has one bit of information,
`  532.4` and an optimal code for symbols following this distribution would spend
`  536.7` only one bit on each such symbol, so the total entropy of Q is one bit.
`  541.5` And what about cross entropy?
`  542.9` If this code was used when a new distribution of symbols applies,
`  546.1` what would the average number of bits per symbol be in that case?
`  549.3` Well, in this example, actually, because each symbol has the same amount of information,
`  554.2` one bit, the weights in the weighted sum don't actually make any difference,
`  558.4` so cross entropy is also one bit.
`  560.7` But now think about flipping this around.
`  562.5` Suppose that Q was the very skewed distribution with the 90-10 split,
`  566.3` while P was an even distribution with the 50-50 split.
`  569.9` Now, from Q's perspective, that one much more likely event has very little information,
`  574.7` and the other one has a lot of information.
`  577.2` So as far as Q is concerned, a perfect code for symbols following this distribution
`  582.1` should spend much less than one bit, again, averaged over all messages,
`  586.3` for that one common symbol, trading off spending multiple bits on average for that
`  591.2` second symbol.
`  592.7` When you calculate it, the total entropy of Q is now smaller than one bit.
`  597.2` But now what about cross entropy?
`  599.1` If a code optimized for this skewed distribution was faced against
`  602.8` a new reality where both events are equally likely,
`  605.8` now you really do see a disadvantage, and that weighted sum is around 1.74 bits.
`  610.8` So stepping back, notice how much order matters here.
`  613.4` When we swapped the roles of P and Q, the value of this cross entropy changed,
`  617.8` which makes sense.
`  619.0` In the formula, the roles of P and Q are pretty different.
`  622.5` While we're here, by the way, just showing simple distributions
`  625.2` over only two possible outcomes, we can have some more fun.
`  628.1` Notice how this distribution Q depends on only one free variable, little q sub 1,
`  632.9` and the complementary value has to be locked at 1 minus little q sub 1.
`  637.8` And same deal for P.
`  639.2` It really depends on just one parameter, little p sub 1.
`  642.6` The reason we can have some fun is that with so few free parameters,
`  645.8` we can build more intuition by graphing things,
`  648.0` which lets me highlight one critical property here.
`  650.8` I want you to imagine fixing P in place and then plotting
`  654.2` this cross entropy expression as a function of Q.
`  657.6` What you'll notice is this graph reaches a very clear minimum, and more specifically,
`  662.4` the value where it achieves that minimum is the one where P and Q are identical.
`  667.9` And hopefully based on how we motivated it, this should make abundant sense.
`  671.8` Always remember that question cross entropy is asking.
`  674.5` How well does a code optimized for one setting, Q, perform in a different setting, P?
`  680.2` That compression efficiency will obviously be at its best when both settings align.
`  684.8` There's something very fun we can do with this plot that helps to highlight a key point.
`  688.2` What I'm going to do is move around that value P,
`  690.9` which changes the entire shape of the graph, and as I do,
`  694.0` you'll notice I'm tracing out where that minimum value of the graph goes.
`  698.4` That traced out shape is a new curve that I'm drawing in green,
`  701.2` and let me take a moment to ask you, what does this new curve represent?
`  705.7` Well, that minimum value for cross entropy is the most efficient
`  709.1` possible compression when reality follows the distribution P,
`  712.5` and that's exactly what the entropy of P is supposed to represent.
`  716.0` And indeed, in this very simplified setting where we're dealing with
`  719.6` a distribution over only two possible outcomes,
`  722.1` this green curve is what the entropy of P would look like as a function
`  725.8` of little p sub 1.
`  728.7` This graph emphasizes the one key point about cross entropy that I want
`  732.7` you to remember from this video, which is that if you think of P as fixed
`  736.9` and Q as the variable, it takes on its smallest possible value when Q is equal to P,
`  741.8` and more specifically, that smallest value is the entropy of P.
`  745.4` It's a little harder to visualize in general, because usually these
`  748.7` are distributions over many more than just two possible outcomes,
`  751.9` but here's one way that you might hold that same fact in your head.
`  755.9` We'll take that core diagram that we built up, I'm going to keep P,
`  759.3` the width of all the bars, fixed, and the distribution Q is going to be variable.
`  763.9` Remember, Q is what determines the height of all of these bars,
`  766.8` those negative log base 2 values.
`  768.8` And again, that key fact is that this value is bound by a certain minimum,
`  773.1` that it achieves that minimum when Q is equal to P,
`  776.2` and that the minimal value is the entropy of P.

## [780s] Application to language trees

`  779.8` Before explaining why this key property makes cross entropy such a good fit for training
`  784.4` large language models, I want you to take a moment to think about how that opening
`  788.7` example of zipping and language trees is basically an application of cross entropy.
`  793.9` Remember what the key idea there was, where if you want to measure how
`  797.4` different two different text documents are, we'll call them A and B,
`  800.8` you take a little snippet of B, tack it onto A, and then compress the result.
`  805.3` You then compare the size of that compressed file to
`  807.9` the size of what you get just compressing A on its own.
`  811.2` Again, because the zipping in that first context is mostly
`  814.1` optimized for the patterns of document A, computing this
`  817.0` difference is basically asking the same question cross entropy does.
`  820.8` How well does a compression scheme optimized for
`  823.5` one context perform when faced with another context?
`  826.4` I am glossing over a couple details where the specific distance metric
`  829.7` that the authors defined was a little more complicated than this,
`  832.9` but the core of it really is this difference that I've been showing.
`  836.7` Now this is not exactly cross entropy for a number of reasons.
`  840.1` One, it's not comparing two different probability distributions.
`  843.5` Instead, it's kind of like retreating a text document from one
`  846.7` language as a sample from some distribution, and hence this
`  849.7` difference is kind of like an empirical estimate of cross entropy.
`  853.7` And even then, it can't be a very good estimate because gzip
`  856.7` is not perfect compression achieving the Shannon limit.
`  859.9` Very far from it.
`  860.8` The algorithm underlying it is a much more straightforward way to find repetitions of
`  865.2` a given text sequence and replace later instances with pointers to earlier instances.
`  870.2` But the author's idea was that, insofar as this approximates cross entropy,
`  874.2` you can still get a useful distance measure, letting you do a
`  877.5` legitimately interesting natural language processing task.
`  881.0` This is a common theme for how cross entropy gets used in practice.
`  884.5` It comes up whenever you have a feeling of wanting to quantify how
`  888.1` different the patterns in one setting are from those in another.
`  892.2` Here, that means the patterns of one language compared to that of another,

## [896s] Pre-training LLMs

`  895.6` but this transitions nicely to our primary application for today,
`  898.7` which is training language models.
`  900.8` Here, what you want to quantify is how different a model's understanding of language is
`  905.1` from the true patterns of language, at least as represented by a bunch of training data.
`  910.0` This animation I've been flashing, by the way,
`  912.0` shows the underlying architecture of a transformer It's something a friend of mine made.
`  916.3` But moving forward, I'm going to switch to something a little bit more schematic,
`  920.0` simply representing a black box controlled by some large number of tunable parameters.
`  925.0` I'm assuming most viewers will have some familiarity
`  927.4` with language models and neural networks.
`  929.6` These are topics that we have hit on on the channel before.
`  932.2` But here's a very quick recap of the basics for what you need to know.
`  936.1` Modern language models divide text into tokens,
`  938.4` which are typically words or pieces of words.
`  941.2` And you think of a language model as a function,
`  943.9` a function that takes as an input any possible piece of text,
`  947.5` thought of as a sequence of tokens, and it produces as an output a probability
`  952.1` distribution over all possible tokens.
`  954.7` And you think of that output as its prediction for what might come next.
`  958.6` To train one of these models, what you need is a loss function,
`  962.0` a way to quantify whether the predictions that it makes are generally good or
`  966.3` generally bad.
`  967.5` A loose intuition, you might imagine, is the graph of a loss function as
`  971.2` something like this, some surface where you're hunting for the minimum.
`  975.4` But you have to take any image like this with a heavy grain of salt because this is a
`  979.9` graph of a function with two inputs, the variables x and y,
`  983.2` whereas a true loss function takes as its input the many billions of parameters
`  987.4` characterizing the language model.
`  989.8` So the real image we want to look at here would have to live in billions of dimensions.
`  994.1` Still, it's enough to reference the core idea,
`  996.7` which is how training looks like tweaking and tuning these models in
` 1000.5` a somewhat automatic way to take steps down this hill, decreasing the value of that loss.
` 1006.1` The automatic process for this tweaking and tuning
` 1008.5` comes down to gradient descent and backpropagation.
` 1011.3` I have done videos on these if you want the details.
` 1013.8` But the point I want to emphasize is that for you, the engineer,
` 1017.0` trying to train a model, once you define a good loss function, you're essentially done.
` 1021.6` The standard machinery of deep learning takes it from there.
` 1024.5` The loss you define is with respect to some big pile of training data,
` 1028.2` which in the language model context would look like many,
` 1031.3` many samples of text typically drawn from the Internet.
` 1034.9` So the key design question for you is what mathematical function can you write
` 1039.0` down describing how well the model performs on all of this data,
` 1042.4` such that the act of minimizing that function is the same thing as improving
` 1046.5` model performance.
` 1048.4` A very nice way to think about the loss function we use in this case is that
` 1052.3` you measure the average information per token from the model's perspective.
` 1057.0` Here's what I mean by that.
` 1058.0` For a given example snippet of text in that data,
` 1060.6` you would compute the probability that the model gives to each new token in there.
` 1065.6` That is, for every initial subsequence of tokens, like this one,
` 1069.0` you have the model predict what would come next,
` 1071.5` and then you look at the true next token, the one that actually showed up
` 1075.4` in this training example, and you consider what probability did the model
` 1079.3` give to that one, that true next token.
` 1081.9` That probability is what I'm representing with the
` 1084.2` little pie charts below each one of these tokens.
` 1086.4` The models are actually specifically designed to give
` 1089.4` you all of these probabilities on a single pass.
` 1092.9` When I say the loss is the average information from the model's perspective,
` 1096.9` what I mean is we take the negative log of all these probabilities.
` 1101.0` As we've discussed multiple times by now, you can
` 1103.5` think of that as measuring how surprising an event is.
` 1106.7` You would expect a smarter model that's really following what's going on to
` 1110.5` generally be unsurprised by what it sees, meaning it gives the true next
` 1114.2` token's higher probabilities, so all these information values would be lower,
` 1118.2` while a randomized or poorly trained model would just be very confused.
` 1122.1` It would give everything a low probability and be surprised all the time.
` 1125.9` Pulling up that graph of the negative log that we were playing with last time,
` 1129.4` this is hopefully very intuitive as a choice for the loss function.
` 1132.9` It's effectively telling you the model is punished, and punished very steeply,
` 1136.7` if it assigns a very low probability to the true next token,
` 1139.7` whereas if that probability is high, that prediction would contribute only a tiny
` 1143.7` amount to the total loss.
` 1145.3` But the thing is, a lot of functions have this same general qualitative shape,
` 1149.5` so a question that I want to be hanging in your mind right now is
` 1153.1` why information specifically would be the best choice here.
` 1156.6` What is it that makes logs special among all the functions with this shape?
` 1161.3` One small nuance is that in machine learning, you almost
` 1163.9` always use the natural log instead of a log base 2.
` 1166.8` This doesn't really matter, the two expressions differ by a constant factor,
` 1170.2` so it's all getting absorbed in something called the learning rate anyway.
` 1173.4` The motive is just that natural logs are a lot cleaner whenever you're
` 1176.9` taking derivatives, and derivatives are the core part of the gradient
` 1180.3` descent algorithm used to concretely decrease the value of this loss function.
` 1185.8` And in some sense, that's it.
` 1187.5` That's really all there is to pre-training.
` 1189.5` All you're doing is looking through each token,
` 1191.8` taking the negative log of the probability the model gives to it,
` 1195.0` and averaging that over every token you see.
` 1197.6` And of course, it's not every token in just one example,
` 1200.1` it's every token in the entirety of the vast, vast training set,
` 1203.1` which you hope represents a significant sample of the language you're trying to model.
` 1208.3` Of course, there really is more to it.
` 1210.0` I've glossed over things like batching or specific optimizers,
` 1213.1` and getting this to run at the mind-boggling scales used in practice is a complete
` 1217.3` engineering feat.
` 1218.5` But at the level of abstraction of just thinking of loss functions,
` 1221.5` it really is remarkably simple.
` 1223.0` It really is just the average information per token,
` 1225.6` assuming all the machinery of deep learning can do its job to minimize this loss,
` 1229.7` hopefully getting it to approach something like the entropy of language,
` 1233.4` what you'd be left with would be a powerful general predictor.

## [1238s] What makes this loss function best?

` 1238.0` You might think this loss function would go by a name like information loss, or log loss,
` 1242.8` but in fact, people call it cross-entropy loss,
` 1245.3` which at first might sound really strange, given that nowhere in the explanation have we
` 1250.0` actually used the cross-entropy formula.
` 1253.0` Now there is one very unsatisfying way that this is commonly described,
` 1257.0` where you say, we are calculating cross-entropy,
` 1259.8` but it's between the model's output on a given token,
` 1262.9` and a fully skewed distribution with all the probability mass concentrated
` 1267.2` on just the one true next token.
` 1269.7` If you pull up the formula we had earlier, where we're taking a weighted sum,
` 1273.1` using all these quantities on the right as weights,
` 1275.4` all of the zeros cancel most of the things out,
` 1277.6` and all you're left with is the negative log of the probability the
` 1280.6` model gives to the true next token.
` 1282.6` But if that's all there was to it, this would be very lame, at least in my opinion.
` 1286.4` This does nothing to explain why you're using cross-entropy in the first place,
` 1290.1` and if it all just evaporates away anyway, why not just be straightforward?
` 1294.1` Why not just call it log loss, or information loss?
` 1297.9` Let me show you what I find more satisfying, which is to start by
` 1300.9` explaining why the choice of logarithms here is not really a choice at all.
` 1304.8` Your hand is almost forced into it, and when you see how,
` 1307.6` the formula for cross-entropy just naturally pops right out in front of you.
` 1312.4` So far we've only focused on one example at a time,
` 1315.0` one specific token prediction from one snippet of text,
` 1317.8` and in our framing we want to turn the probability that the model gives to that
` 1321.9` token into some kind of loss, some value, telling the model how bad it should
` 1325.9` feel and how aggressively it should correct itself.
` 1329.1` Now at first, it looks like the only real constraint
` 1331.3` is that this should be a decreasing function.
` 1333.7` You want to assign high loss to low probabilities,
` 1336.9` and low loss to probabilities closer to 1.
` 1340.1` So given the infinite abundance of functions with this rough shape,
` 1343.0` what makes one of them better than the others?
` 1345.5` Let's say we don't know right now, so whatever choice we make,
` 1348.1` we're going to label it as F, and see if we can find some other
` 1350.8` property that we want F to have, something that might force our hand.
` 1354.6` And for this, imagine an example like myName is blank.
` 1358.2` This is a small enough and common enough pattern that you would be likely
` 1361.3` to see many different instances of it show up in your pre-training data.
` 1364.8` What you might imagine is very common names show up multiple times in the data,
` 1368.6` while rare names show up less frequently.
` 1370.6` When you feed in these tokens, myName is, into the model,
` 1373.7` it produces some distribution over all possible next tokens,
` 1377.1` and so let's label the probabilities in the model's distribution of
` 1380.8` outputs with the letter Q.
` 1383.0` Now let me ask you, what is the total loss associated with this prediction?
` 1387.4` If you were just focused on one instance where this pattern shows up in
` 1390.8` the training data, that loss looks like F of Q for whatever your choice
` 1394.3` of the function F is, whether that's a negative log or something else.
` 1397.7` But the key is that this is only one part of the total loss associated with the example.
` 1402.5` Every other instance of this name also contributes that same amount,
` 1406.0` and each instance of every other name also contributes an analogous amount,
` 1409.9` except where you input the probabilities that the model gives to those other names.
` 1414.6` Here, I'll use the letter P to represent the proportion
` 1417.4` of times that a given name shows up in the training data.
` 1420.8` The average value for the loss of the model's output over all of the examples
` 1424.8` that have this pattern looks like a weighted average, weighted by these values P.
` 1429.9` From here, maybe you can start to anticipate the role of cross entropy.
` 1433.3` If you choose to make this function F the negative log of Q,
` 1436.7` then this full expression for the total average loss associated
` 1440.2` with the input text really is exactly the definition of cross entropy.
` 1444.8` Specifically, it's the cross entropy of our model's output
` 1448.4` relative to the statistics represented within the data.
` 1452.2` And remember the one key property of this formula I want you to remember.
` 1455.6` It's something that takes on a minimum exactly when
` 1458.4` all these P and Q values are equal to each other.
` 1461.6` So in this setting, that would mean it's minimized exactly when the distribution your
` 1465.7` model outputs is the same as the statistical distribution represented in your data.
` 1470.3` But the real key point is that this implication goes the other way around.
` 1473.9` If we switch back to writing this per example loss with some generic function F,
` 1478.3` and you say you would like it to be the case that the full average loss over all of the
` 1483.2` examples is minimized only when the model's output matches the statistics that show up
` 1488.0` in the data, there's actually a really nice mathematical argument for why F has to be a
` 1492.9` logarithm.
` 1494.0` I'm hesitant to derail us too much by delving into the details,
` 1496.9` which involves something called a Lagrange multiplier,
` 1499.4` since there's a risk of losing the forest for the trees.
` 1502.4` I know many of you are curious, so I will pull up the details on the screen
` 1505.8` for any multivariable calculus enthusiasts interested in pausing and pondering.
` 1509.8` The high-level idea really is very pretty.
` 1511.8` It's that to minimize our key expression, subject to the condition that the
` 1515.6` sum of all the q values is equal to one, you end up with a problem that looks
` 1519.6` like finding values where two different contours are tangent to each other.
` 1523.8` You compute where that happens by setting a pair of gradient values equal to each other,
` 1528.4` and this, for our specific expressions, will boil down to the condition
` 1532.3` that the derivative of our function F with respect to q has to look like
` 1536.2` some constant over q, and only logarithms have that property.
` 1539.5` Again, I pull this up just for the extra curious.
` 1542.4` The details are not too important.
` 1544.4` The main thing I want you to know is that if you want a loss
` 1547.3` function with the property that it's minimized only when the
` 1550.3` model matches the statistics of the data, your hand is forced.
` 1553.6` You actually have to use the negative log.
` 1555.7` And in this case, the average loss associated with any given
` 1558.9` input text looks exactly like the cross-entropy formula.
` 1563.0` And while I'm here throwing up notes for the extra curious,
` 1565.4` here's another one about overfitting and how magical it is that this
` 1568.3` actually works when you stop and think about the sparsity of the data that we have.

## [1573s] Distillation

` 1573.3` The last topic I want to hit on in this section is an interesting variant on
` 1576.7` training language models where this cross-entropy formula is used more explicitly.
` 1581.1` And it's a case where each training example gives a much softer tug on the model's
` 1585.4` distributions, one that is not so over-weighted to one specific next token.
` 1590.2` It's something called distillation.
` 1592.3` The setup here is that you might want to train a relatively small model where its
` 1596.6` goal is to approximate the performance of some larger, presumably much smarter model.
` 1601.9` This comes up all the time, because very often after getting some desired performance by
` 1606.0` scaling up all of your parameters, what you would love is to be able to approximate that
` 1610.1` performance with something much smaller and much more efficient to run at inference time.
` 1614.9` The idea is that with a bigger model in hand, you have the ability to do something much,
` 1618.9` much more efficient than normal pre-training with that small model.
` 1622.3` What you do is look through a bunch of data, and as before, at each new token,
` 1626.1` you consider the small model's prediction of what will follow, that full distribution.
` 1631.0` But now, instead of just comparing it to the true next token in the data,
` 1634.8` you compare it to the larger model's prediction,
` 1637.3` its full distribution across all the tokens at that same point.
` 1641.1` You define the loss at this token to be the cross-entropy of
` 1644.6` the small model's distribution relative to the big model's.
` 1648.7` When you think about it, this gives you something much,
` 1651.4` much richer than ordinary pre-training, since pre-training is just
` 1654.6` giving full weight to only one true next token, the one that happens to be there.
` 1659.0` As an analogy, it's the difference between trying to learn chess just by
` 1662.6` watching a game versus having someone better than you talk through all the
` 1666.4` possible good moves and how heavily they would weight them at each new turn.
` 1671.8` Looking back at that My Name is Blank example,
` 1674.2` instead of having to see many thousands or many millions of examples in the data
` 1678.4` before your loss represents the cross-entropy against a reasonable distribution of
` 1682.6` possible names, you can get that same effect just on a single example,
` 1686.3` comparing it against the good model's prediction.
` 1690.7` I think now is a good time to zoom out and look over everything we've built up.
` 1694.8` In the first half, in the context of compression,
` 1697.4` cross-entropy arose very naturally just by asking how well a compression scheme
` 1701.5` optimized for one setting performs in another.
` 1704.8` The mild surprise is that this idea turns out to be much more generally useful,
` 1708.7` as a way to measure how different patterns in one setting are from those in another.
` 1713.4` This is what makes it such a common tool for loss functions in modern machine learning.
` 1717.5` All that said, as stated so far, the way that the formula showed up in the second half,
` 1721.4` for us, feels pretty different from the way that it showed up in the first half.
` 1725.4` It was essentially unrelated to compression.
` 1727.7` The logic actually came from a completely different part of math,
` 1730.5` constrained optimization.
` 1732.2` But I wouldn't be putting these two topics in the same
` 1734.4` video if they didn't have a tighter connection than that.
` 1736.7` In the same way that whenever you see pi show up in math,
` 1739.4` even when it seems unrelated to circles, there's always going to be some connection to
` 1743.6` circles hiding there, I think whenever you see cross-entropy pop up,
` 1746.9` there will be a way to connect it to compression.
` 1750.3` And in the case of language models, we've already teed things up for how
` 1753.7` to make that connection a little bit more tight by describing the loss
` 1757.0` function as the average information per token, from the model's perspective.
` 1761.6` The next step from here is to explain how it's possible
` 1764.7` to turn a general predictor into a compressor.
` 1767.7` For instance, turning a language model, this prediction machine,
` 1770.9` into a language compressor.
` 1772.6` More specifically, one where the number of bits that you use
` 1775.8` to represent a piece of text will approximately match the
` 1778.8` information content of that text, from the model's perspective.
` 1782.6` It's actually very surprising this is even possible.
` 1785.0` There's one very visual and very beautiful compression algorithm showing how
` 1788.4` to do exactly this that you and I are going to dig into in the next part.
` 1791.9` And once you understand this, it makes clear how using cross-entropy loss is
` 1796.1` actually equivalent to training the model to be the best possible text compressor.
` 1801.3` This, in turn, gives us a nice hill to stand on where we can look over the landscape
` 1805.8` and assess that thought-provoking phrase, compression is intelligence, head-on.

## [1812s] 3b1b Talent

` 1812.1` I do want to add one final footnote to this video,
` 1814.6` because it would be a shame not to at least quickly explain a related concept
` 1818.4` called KL divergence, which you also see all the time littered throughout
` 1822.0` machine learning papers.
` 1823.5` Before I jump into that, I want to make a very quick plug for 3b1b talent,
` 1827.1` because there's actually a puzzle on that page that is directly related to KL divergence.
` 1832.2` For context, this is something like a virtual career fair that I've put together this
` 1836.2` year, where the premise is to have a set of partnered organizations that are interesting
` 1840.4` places to work, who are also keen to hire the kinds of people like you,
` 1843.8` people who watch videos about things like the relationship between compression and
` 1847.8` intelligence.
` 1848.8` One of the main features of that page is a set of interviews that I did with
` 1852.1` the various teams, which I think is just a much better way to let you get to
` 1855.5` know the culture of a company than trying to just read a generic jobs page.
` 1859.2` But another thing you'll find is that many companies there have
` 1862.3` featured challenges specifically for this audience,
` 1864.9` where you are often invited to mention your solution in an application.
` 1868.9` Now, this was not at all planned, but by happenstance,
` 1871.5` the challenge that one of the companies, Dopple, put up there,
` 1874.6` happens to use the formula for KL divergence.
` 1877.4` They didn't know I was planning this video, so you can take this as a nice bit of
` 1880.9` evidence that the math I'm teaching you here really does show up out in the real world.
` 1885.1` This is just one example, but you can find a number of other interesting places
` 1889.7` to work with nice puzzles and challenges for you to try out at 3b1b.co/talent.

## [1895s] KL Divergence

` 1895.3` Okay, so what is KL divergence?
` 1897.7` Remember that key property of cross entropy that I want you to come away remembering?
` 1901.7` The fact that it takes on a minimal value when p and q are the same,
` 1905.7` and that that minimum is equal to the entropy of p.
` 1909.1` This makes it very natural to want to give a name to
` 1911.8` describe the difference between these two values.
` 1914.7` And indeed, this difference has the special name,
` 1917.4` it is the Kolbach-Leibler divergence, commonly abbreviated to KL divergence.
` 1922.0` In the language of compression, you would think of it as describing how
` 1925.7` many bits per symbol are you wasting by using a poorly optimized code.
` 1930.0` For example, in our robot case, if you take the bits per symbol in the
` 1933.7` unoptimized case minus the bits per symbol in the optimized case,
` 1937.1` that difference gives you the KL divergence between the two distributions.
` 1942.0` It's specifically telling you how wasteful you are.
` 1944.9` In the machine learning setting, KL divergence acts
` 1947.2` as a kind of distance measure between distributions.
` 1950.1` It's zero when both of them are the same, but it grows as they differ.
` 1953.9` It's not exactly a difference though, because it's asymmetric.
` 1957.2` The KL divergence of q relative to p is not the same as that of p relative to q.
` 1962.6` To cap off today, I want to leave you with three
` 1964.8` things to ponder related to this expression.
` 1967.2` The first one is easy, which is how when you see it in practice,
` 1969.8` it often comes up in this more compact form, and I just want you
` 1972.5` to convince yourself that these two expressions really are the same.
` 1975.8` The compact form hides the fact that it's really just a difference
` 1978.6` between cross entropy and entropy, but it is more succinct.
` 1981.9` Secondly, I've been showing this diagram, a variant on our cross entropy diagram.
` 1985.8` I want to see if you can take a moment to convince yourself
` 1988.4` in what sense this is representing our expression.
` 1991.2` And third, I mentioned that when you distill a large model into a smaller one,
` 1995.0` you use the cross entropy between their distributions as a loss function.
` 1999.0` I want you to ask yourself, what would happen if instead you used the KL divergence?
` 2003.2` After all, if the KL divergence is like a distance measure,
` 2005.9` wouldn't this be a more natural choice?