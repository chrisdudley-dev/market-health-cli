package dev.chrisdudley.markethealth

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class NavigationTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @After fun removeTestHolding(): Unit = kotlinx.coroutines.runBlocking {
        CoreRepository.get(androidx.test.platform.app.InstrumentationRegistry.getInstrumentation().targetContext)
            .call("remove", org.json.JSONObject().put("symbol", "IVE").put("account", "Other"))
    }

    @Test fun allEightNativeDestinationsOpen() {
        for (name in listOf("Portfolio", "Trading List", "Buy Candidates", "Market Health", "History", "Policy", "Settings", "Dashboard")) {
            rule.onNodeWithTag("open-menu").performClick()
            rule.onNodeWithTag("drawer-" + Destination.entries.first { it.title == name }.name).performScrollTo().performClick()
            rule.onNodeWithTag("page-title").assertTextEquals(name)
        }
    }

    @Test fun manualHoldingCanBeSavedAndRemoved() {
        rule.onNodeWithTag("open-menu").performClick()
        rule.onNodeWithTag("drawer-PORTFOLIO").performScrollTo().performClick()
        rule.onNodeWithTag("add-holding").performClick()
        rule.onNodeWithTag("holding-symbol").performTextInput("IVE")
        rule.onNodeWithTag("holding-shares").performTextInput("3")
        rule.onNodeWithTag("save-holding").performClick()
        rule.waitUntil(30_000) { rule.onAllNodesWithText("IVE").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("IVE").assertIsDisplayed()
        rule.onNodeWithTag("remove-IVE").performScrollTo().performClick()
        rule.onNodeWithText("Keep holding").performClick()
        rule.onNodeWithText("IVE").assertIsDisplayed()
        rule.onNodeWithTag("edit-IVE").performScrollTo().performClick()
        rule.onNodeWithTag("holding-shares").performTextReplacement("4")
        rule.onNodeWithTag("save-holding").performClick()
        rule.waitUntil(30_000) { rule.onAllNodesWithText("4.0").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithTag("remove-IVE").performScrollTo().performClick()
        rule.onNodeWithTag("confirm-remove").performClick()
        rule.waitUntil(30_000) { rule.onAllNodesWithText("IVE").fetchSemanticsNodes().isEmpty() }
    }
}
