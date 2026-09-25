pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "shaggyrs6.briefing"
    manageIpc: false
    property var anchorItem: null
    property var hostWidget: null
    property var briefingData: ({news: [], transactions: [], sources: [], settings: {intervalHours: 0, enabledSources: []}, unread: 0})
    property string errorMessage: ""
    property string currentView: "updates"
    property bool officialOnly: false
    property bool unreadOnly: false
    property bool showHistory: false
    property bool showOlderMise: false
    readonly property var miseData: briefingData.mise || ({installed: [], history: [], error: null})
    property var intervals: [0, 2, 6, 8, 12, 24]
    readonly property color ink: bar ? bar.foreground : Color.foreground
    readonly property color accent: Color.accent
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("briefing.py").toString().replace(/^file:\/\//, ""))
    readonly property var visibleNews: briefingData.news.filter(function(item) {
        return (!root.officialOnly || item.source === "official" || item.source === "releases") && (!root.unreadOnly || !item.read)
    })
    readonly property var visibleTransactions: briefingData.transactions.filter(function(tx) {
        return root.showHistory || tx.started.substring(0, 10) === root.briefingData.transactions[0].started.substring(0, 10)
    })
    function open() { run(["status"]); root.controller.show() }
    function close() { root.controller.hide() }
    function run(args) {
        if (worker.running) return
        root.errorMessage = ""
        worker.command = ["python3", root.helper].concat(args)
        worker.running = true
    }
    function act(payload) { run(["action", JSON.stringify(payload)]) }
    function date(value) { return value ? new Date(value).toLocaleString() : "Never" }
    function setSource(sourceId, enabled) {
        var sources = root.briefingData.settings.enabledSources.slice()
        var index = sources.indexOf(sourceId)
        if (enabled && index < 0) sources.push(sourceId)
        if (!enabled && index >= 0) sources.splice(index, 1)
        act({action: "settings", settings: {intervalHours: briefingData.settings.intervalHours, enabledSources: sources}})
    }
    Process {
        id: worker
        stdout: StdioCollector { id: output; waitForEnd: true }
        stderr: StdioCollector { id: errors; waitForEnd: true }
        onExited: function(code) {
            try {
                var value = JSON.parse(output.text)
                if (code !== 0 || value.error) root.errorMessage = value.error || "Could not read briefing data."
                else root.briefingData = value
            } catch (e) { root.errorMessage = "Could not read briefing data. " + errors.text.substring(0, 200) }
        }
    }
    Component.onCompleted: run(["refresh", "--due"])
    Timer {
        interval: 60000
        repeat: true
        running: true
        onTriggered: if (!worker.running) root.run(["refresh", "--due"])
    }
    component Copy: Text {
        color: root.ink
        font.pixelSize: Style.font.body
        font.family: Style.font.family
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        Layout.fillWidth: true
    }
    component Action: Controls.Button {
        id: control
        enabled: !worker.running
        implicitHeight: Style.space(42)
        contentItem: Text {
            text: control.text
            color: root.ink
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: Style.space(6)
            color: control.down ? Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.18) : "transparent"
            border.width: control.activeFocus ? 2 : 1
            border.color: control.activeFocus ? root.accent : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.3)
        }
    }
    KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: content
        contentWidth: popup.fittedContentWidth(Style.space(600))
        contentHeight: popup.fittedContentHeight(Style.space(720))
        FocusScope {
            id: content
            anchors.fill: parent
            Keys.onEscapePressed: root.close()
            ColumnLayout {
                anchors.fill: parent
                spacing: Style.space(12)
                Copy { text: "Omarchy Briefing"; font.pixelSize: Style.font.subtitle; font.bold: true }
                RowLayout {
                    Layout.fillWidth: true
                    Action { text: "Omarchy Updates Explained"; onClicked: root.currentView = "updates" }
                    Action { text: "Omarchy News · " + root.briefingData.unread; onClicked: root.currentView = "news" }
                    Action { text: "Settings"; onClicked: root.currentView = "settings" }
                }
                Copy { visible: root.errorMessage !== ""; text: root.errorMessage; color: "#e7c889" }
                Copy { visible: worker.running; text: "Checking… saved content remains below." }
                Controls.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: Style.space(12)
                        ColumnLayout {
                            visible: root.currentView === "updates"
                            Layout.fillWidth: true
                            Copy { text: root.briefingData.coverage || "Reading local package history…"; font.pixelSize: Style.font.caption }
                            Copy { text: "Installed tools · mise"; font.bold: true; color: root.accent }
                            Copy { visible: !!root.miseData.error; text: (root.miseData.error || "") + " Saved observations may be stale."; color: "#e7c889" }
                            Copy { text: "Checked " + root.date(root.miseData.checkedAt) + ". First seen is when Briefing noticed a version, not its installation time."; font.pixelSize: Style.font.caption }
                            Action { text: root.showOlderMise ? "Show selected versions" : "Show all installed tool versions"; onClicked: root.showOlderMise = !root.showOlderMise }
                            Repeater {
                                model: root.miseData.installed.filter(function(x) { return root.showOlderMise || x.active })
                                delegate: ColumnLayout {
                                    id: toolRow
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Copy { text: toolRow.modelData.title + " · " + toolRow.modelData.version; font.bold: true }
                                    Copy { text: toolRow.modelData.description }
                                    Copy { text: (toolRow.modelData.active ? "Selected in home configuration" : "Installed, not selected") + " · " + (toolRow.modelData.baseline ? "Existing installation discovered" : "New installation observed"); color: root.accent; font.pixelSize: Style.font.caption }
                                    Copy { text: "First seen: " + root.date(toolRow.modelData.firstSeen); font.pixelSize: Style.font.caption }
                                }
                            }
                            Repeater {
                                model: root.miseData.history.slice(0, 20)
                                delegate: Copy {
                                    required property var modelData
                                    text: modelData.title + " " + modelData.version + " · " + modelData.event + "\nObserved between " + root.date(modelData.since) + " and " + root.date(modelData.at)
                                    font.pixelSize: Style.font.caption
                                }
                            }
                            Copy { text: "Package transactions"; font.bold: true; color: root.accent }
                            Copy { visible: !!root.briefingData.logError; text: root.briefingData.logError || ""; color: "#e7c889" }
                            Action { text: root.showHistory ? "Show latest day" : "Show recent history"; onClicked: root.showHistory = !root.showHistory }
                            Copy { visible: root.briefingData.transactions.length === 0; text: "No recorded package changes found." }
                            Repeater {
                                model: root.visibleTransactions
                                delegate: ColumnLayout {
                                    id: transaction
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Copy { text: root.date(transaction.modelData.started) + " · " + transaction.modelData.status; color: root.accent }
                                    Copy { visible: !transaction.modelData.completed; text: "No completion record. These changes are not confirmed as a completed transaction."; color: "#e7c889" }
                                    Repeater {
                                        model: transaction.modelData.changes
                                        delegate: ColumnLayout {
                                            id: change
                                            required property var modelData
                                            property bool expanded: false
                                            Layout.fillWidth: true
                                            Copy { text: change.modelData.title + " · " + change.modelData.action; font.bold: true }
                                            Copy { text: change.modelData.description }
                                            Copy { text: (change.modelData.oldVersion && change.modelData.newVersion && change.modelData.oldVersion !== change.modelData.newVersion ? change.modelData.oldVersion + " → " : "") + (change.modelData.newVersion || change.modelData.oldVersion); color: root.accent }
                                            Copy { text: change.modelData.changeKind; font.pixelSize: Style.font.caption }
                                            Action { text: change.expanded ? "Hide details" : "Changes & evidence"; onClicked: change.expanded = !change.expanded }
                                            ColumnLayout {
                                                visible: change.expanded
                                                Layout.fillWidth: true
                                                Copy { text: change.modelData.releaseNote }
                                                Copy { text: change.modelData.releaseScope || ""; visible: text !== ""; font.pixelSize: Style.font.caption }
                                                Copy { text: change.modelData.actionNote; font.pixelSize: Style.font.caption }
                                                Action { visible: !!change.modelData.sourceUrl; text: change.modelData.releaseUrl ? "Open release announcement" : "Browse source (version not matched)"; onClicked: Qt.openUrlExternally(change.modelData.releaseUrl || change.modelData.sourceUrl) }
                                                Copy { text: root.briefingData.logPath + ":" + change.modelData.line + "\n" + change.modelData.evidence; font.pixelSize: Style.font.caption }
                                            }
                                            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: root.ink; opacity: 0.2; Layout.topMargin: Style.space(8); Layout.bottomMargin: Style.space(8) }
                                        }
                                    }
                                    Repeater {
                                        model: transaction.modelData.rebuilds
                                        delegate: Copy { required property var modelData; text: modelData.description; color: root.accent }
                                    }
                                }
                            }
                        }
                        ColumnLayout {
                            visible: root.currentView === "news"
                            Layout.fillWidth: true
                            Copy { visible: !!root.briefingData.newsError; text: root.briefingData.newsError || ""; color: "#e7c889" }
                            RowLayout {
                                Action { text: "Refresh news"; onClicked: root.run(["refresh"]) }
                                Action { text: root.officialOnly ? "Official only ✓" : "Official only"; onClicked: root.officialOnly = !root.officialOnly }
                                Action { text: root.unreadOnly ? "Unread only ✓" : "Unread only"; onClicked: root.unreadOnly = !root.unreadOnly }
                            }
                            RowLayout {
                                Action { text: "Mark all read"; onClicked: root.act({action: "read", ids: root.briefingData.news.map(function(x) { return x.id }), read: true}) }
                                Action { text: "Mark shown as read"; onClicked: root.act({action: "read", ids: root.visibleNews.map(function(x) { return x.id }), read: true}) }
                            }
                            Repeater {
                                model: root.briefingData.sources.filter(function(x) { return x.enabled })
                                delegate: Copy {
                                    required property var modelData
                                    text: modelData.name + " · checked " + root.date(modelData.lastSuccess) + (modelData.error ? "\n" + modelData.error : "")
                                    font.pixelSize: Style.font.caption
                                    color: modelData.error ? "#e7c889" : root.ink
                                }
                            }
                            Copy { visible: root.visibleNews.length === 0; text: "No headlines in this view. Refresh news or check your filters and sources." }
                            Repeater {
                                model: root.visibleNews
                                delegate: ColumnLayout {
                                    id: story
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Copy { text: story.modelData.label + " · " + root.date(story.modelData.published) + (story.modelData.read ? " · Read" : " · Unread"); font.pixelSize: Style.font.caption; color: root.accent }
                                    Copy { text: story.modelData.title; font.bold: true }
                                    Copy { text: story.modelData.excerpt }
                                    RowLayout {
                                        Action { text: "Read original"; onClicked: { Qt.openUrlExternally(story.modelData.url); root.act({action: "read", ids: [story.modelData.id], read: true}) } }
                                        Action { text: story.modelData.read ? "Mark unread" : "Mark read"; onClicked: root.act({action: "read", ids: [story.modelData.id], read: !story.modelData.read}) }
                                    }
                                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: root.ink; opacity: 0.2; Layout.topMargin: Style.space(8); Layout.bottomMargin: Style.space(8) }
                                }
                            }
                        }
                        ColumnLayout {
                            visible: root.currentView === "settings"
                            Layout.fillWidth: true
                            Copy { text: "Check for news"; font.bold: true }
                            Controls.ComboBox {
                                Layout.fillWidth: true
                                enabled: !worker.running
                                model: ["Manually", "Every 2 hours", "Every 6 hours", "Every 8 hours", "Every 12 hours", "Every 24 hours"]
                                currentIndex: root.intervals.indexOf(root.briefingData.settings.intervalHours)
                                onActivated: root.act({action: "settings", settings: {intervalHours: root.intervals[currentIndex], enabledSources: root.briefingData.settings.enabledSources}})
                            }
                            Copy { text: "Checks run while the desktop shell is running. Saved headlines stay available offline." }
                            Copy { text: "Sources"; font.bold: true }
                            Repeater {
                                model: root.briefingData.sources
                                delegate: Action {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    text: (modelData.enabled ? "✓ " : "+ ") + modelData.name + " · " + modelData.label
                                    onClicked: root.setSource(modelData.id, !modelData.enabled)
                                }
                            }
                            Copy { text: "Source extracts, not AI summaries. Package history stays local. Notifications are off. Refreshing news never installs software." }
                        }
                    }
                }
            }
        }
    }
}
