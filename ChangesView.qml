pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls as C
import QtQuick.Layouts
import Quickshell.Io
import qs.Commons

Item {
    id: root
    property color ink: Color.foreground
    property color accent: Color.accent
    property bool active: false
    property string stateDirectory: "" // Optional isolated test state; empty uses the existing journal.
    property var journal: ({entries: [], pending: [], checkedAt: "", detectionError: ""})
    property var selected: null
    property string page: "saved"
    property string search: ""
    property string message: ""
    property string action: ""
    property string payload: ""
    property string editingId: ""
    property string expected: ""
    property string eventId: ""
    property bool dirty: false
    readonly property color readableAccent: root.accent
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("changes.py").toString().replace(/^file:\/\//, ""))
    readonly property var records: journal.entries.filter(r => (r.title + " " + r.why + " " + r.details + " " + r.kind + " " + r.status).toLowerCase().indexOf(search.toLowerCase()) >= 0)
    function refresh() { if (page !== "edit") run("check") }
    onActiveChanged: if (active) refresh()
    function explain(change, completed) {
        if (page === "edit") { message = "An unsaved draft is already open. Save or discard it first."; return }
        edit(null, null)
        titleField.text = change.title + " · " + change.action
        dateField.text = change.at.substring(0, 10)
        detailField.text = change.package + ": " + (change.oldVersion || "Not installed") + " → " + (change.newVersion || "Removed")
        evidenceField.text = change.evidence + "\n" + (completed ? "Transaction completion recorded." : "Incomplete transaction: completion not confirmed.")
    }
    function run(command, value) {
        if (worker.running) return
        action = command
        message = ""
        worker.command = ["python3", helper]
        if (stateDirectory) worker.command.push("--state-dir", stateDirectory)
        worker.command.push(command)
        if (command === "handled") worker.command.push(value)
        payload = command === "save" ? value : ""
        worker.running = true
    }
    function edit(record, event) {
        editingId = record ? record.id : ""
        expected = record ? record.updatedAt : ""
        eventId = event ? event.id : ""
        titleField.text = record ? record.title : event ? event.name : ""
        dateField.text = record ? record.date : Qt.formatDate(new Date(), "yyyy-MM-dd")
        whyField.text = record ? record.why : ""
        detailField.text = record ? record.details : event ? event.change + ": " + event.before + " → " + event.after : ""
        backupField.text = record ? record.backup : ""
        undoField.text = record ? record.undo : ""
        evidenceField.text = record ? record.evidence : event ? "Observed between " + event.since + " and " + event.at + ". Exact change time and reason are not known." : ""
        kindField.currentIndex = Math.max(0, kindField.model.indexOf(record ? record.kind : event ? event.kind : "Software"))
        statusField.currentIndex = Math.max(0, statusField.model.indexOf(record ? record.status : "Needs checking"))
        page = "edit"
        dirty = false
    }
    function saveRecord() {
        run("save", JSON.stringify({id: editingId, expectedUpdatedAt: expected, record: {
            title: titleField.text, date: dateField.text, why: whyField.text, details: detailField.text,
            backup: backupField.text, undo: undoField.text, evidence: evidenceField.text,
            kind: kindField.currentText, status: statusField.currentText
        }}))
    }
    Process {
        id: worker
        stdinEnabled: true
        onStarted: { if (root.action === "save") write(root.payload); stdinEnabled = false }
        onRunningChanged: if (!running) stdinEnabled = true
        stdout: StdioCollector { id: output; waitForEnd: true }
        stderr: StdioCollector { id: errors; waitForEnd: true }
        onExited: function(code) {
            try {
                const data = JSON.parse(output.text)
                if (code !== 0 || data.error) { root.message = data.error || "Could not load the journal. Your draft is kept."; return }
                root.journal = data
                if (root.action === "save") {
                    root.selected = data.entries.find(r => r.id === data.savedId)
                    root.page = "saved"; root.dirty = false
                    root.message = "Saved. No system settings were changed."
                    if (root.eventId) { const id = root.eventId; root.eventId = ""; Qt.callLater(() => root.run("handled", id)) }
                } else if (root.selected) root.selected = data.entries.find(r => r.id === root.selected.id) || null
                else if (data.entries.length) root.selected = data.entries[0]
            } catch (e) { root.message = "Could not read the journal response. Your draft is kept." }
        }
    }
    Component.onCompleted: run("check")
    Timer { interval: 300000; repeat: true; running: true; onTriggered: if (!worker.running && root.page !== "edit") root.run("check") }

    component Copy: BriefingText { ink: root.ink }
    component Action: BriefingButton { ink: root.ink; accent: root.accent; enabled: !worker.running }
    component Field: C.TextField {
        Layout.fillWidth: true; color: root.ink; placeholderTextColor: Qt.rgba(root.ink.r,root.ink.g,root.ink.b,0.55)
        font.family: Style.font.family; font.pixelSize: Style.font.body; selectByMouse: true
        implicitHeight: Style.space(42)
        background: Rectangle { radius: Style.space(6); color: "transparent"; border.color: Qt.rgba(root.ink.r,root.ink.g,root.ink.b,0.3) }
        onTextChanged: root.dirty = true
    }
    component Area: C.TextArea {
        Layout.fillWidth: true; color: root.ink; placeholderTextColor: Qt.rgba(root.ink.r,root.ink.g,root.ink.b,0.55)
        font.family: Style.font.family; font.pixelSize: Style.font.body
        wrapMode: TextEdit.Wrap; selectByMouse: true; textFormat: TextEdit.PlainText
        background: Rectangle { radius: Style.space(6); color: "transparent"; border.color: Qt.rgba(root.ink.r,root.ink.g,root.ink.b,0.3) }
        onTextChanged: root.dirty = true
    }
    component Choice: C.ComboBox {
        font.family: Style.font.family; font.pixelSize: Style.font.body
        palette.text: root.ink; palette.buttonText: root.ink
        implicitHeight: Style.space(42)
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: Style.space(12)
        Copy { text: root.message; visible: text !== ""; color: root.readableAccent }
        Copy { text: root.journal.detectionError || ""; visible: text !== ""; color: "#e7c889" }
        RowLayout {
            visible: root.page !== "edit"
            Action { text: "Saved (" + root.journal.entries.length + ")"; onClicked: root.page = "saved" }
            Action { text: "Needs context (" + root.journal.pending.length + ")"; onClicked: root.page = "pending" }
            Action { text: "Check now"; onClicked: root.run("scan") }
        }
        RowLayout {
            visible: root.page !== "edit"
            Action { text: "+ Add a change"; onClicked: root.edit(null, null) }
        }
        Copy { visible: root.page !== "edit"; font.pixelSize: Style.font.caption; color: root.readableAccent; text: worker.running ? "Checking…" : root.journal.checkedAt ? "Packages + Omarchy plugins · checked " + Qt.formatDateTime(new Date(root.journal.checkedAt), "dd MMM · HH:mm") : "No baseline yet. Check now to begin automatic detection." }
        ColumnLayout {
            visible: root.page === "saved"; Layout.fillWidth: true; Layout.fillHeight: true; spacing: Style.space(20)
            ColumnLayout {
                Layout.fillWidth: true; Layout.preferredHeight: Style.space(170)
                Field { placeholderText: "Find software, plugins or a reason…"; onTextChanged: root.search = text }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: Style.space(8)
                    model: root.records
                    C.ScrollBar.vertical: C.ScrollBar {}
                    delegate: C.ItemDelegate {
                        id: recordButton
                        required property var modelData
                        width: ListView.view.width
                        contentItem: ColumnLayout {
                            Copy { text: modelData.title; font.bold: true }
                            Copy { text: modelData.date + " · " + modelData.status; font.pixelSize: Style.font.caption; color: root.readableAccent }
                        }
                        highlighted: root.selected && root.selected.id === modelData.id
                        background: Rectangle {
                            radius: Style.space(6)
                            color: recordButton.highlighted || recordButton.down ? Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.18) : "transparent"
                            border.width: recordButton.activeFocus ? 2 : 1
                            border.color: recordButton.activeFocus ? root.accent : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.3)
                        }
                        onClicked: root.selected = modelData
                    }
                }
                Copy { visible: root.records.length === 0; text: root.search ? "No matching records." : "No saved explanations yet. Add a change, or explain an item under Needs context." }
            }
            C.ScrollView {
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width; spacing: Style.space(14)
                    Copy { text: root.selected ? root.selected.title : "Less remembering. More context."; font.pixelSize: Style.font.subtitle; font.bold: true }
                    Copy { text: root.selected ? root.selected.kind + " · " + root.selected.date + " · " + root.selected.status : "The first scan establishes what is installed now—it does not invent past changes. Later package and plugin changes appear under Needs context.\n\nSettings edits and loose AppImages need a manual entry. Nothing here installs, removes or undoes anything." }
                    Action { visible: !!root.selected; text: "Edit record"; onClicked: root.edit(root.selected, null) }
                    Repeater {
                        model: root.selected ? [{label:"WHY", value:root.selected.why}, {label:"WHAT CHANGED", value:root.selected.details}, {label:"BACKUP", value:root.selected.backup}, {label:"HOW TO UNDO — NOTES ONLY", value:root.selected.undo}, {label:"EVIDENCE / SOURCE", value:root.selected.evidence}] : []
                        delegate: ColumnLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Copy { text: modelData.label; color: root.readableAccent; font.pixelSize: Style.font.caption }
                            Copy { text: modelData.value || "Not recorded" }
                        }
                    }
                }
            }
        }
        C.ScrollView {
            visible: root.page === "pending"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: Style.space(14)
                Copy { text: "Detected changes, not explanations. Times show when we noticed—not the exact installation time." }
                Copy { visible: root.journal.pending.length === 0; text: "Nothing waiting for context. Checks run every five minutes while the shell is running. Changes made before the baseline or entirely between checks cannot be reconstructed." }
                Repeater {
                    model: root.journal.pending.slice(0, 100)
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true; spacing: Style.space(6)
                        Copy { text: modelData.name; font.bold: true; font.pixelSize: Style.font.body }
                        Copy { text: modelData.change + " · " + modelData.before + " → " + modelData.after }
                        Copy { text: "Observed " + Qt.formatDateTime(new Date(modelData.at), "dd MMM yyyy HH:mm"); font.pixelSize: Style.font.caption; color: root.readableAccent }
                        RowLayout {
                            Action { text: "Add why / details"; onClicked: root.edit(null, modelData) }
                            Action { text: "No note needed"; onClicked: root.run("handled", modelData.id) }
                        }
                    }
                }
                Copy { visible: root.journal.pending.length > 100; text: "Showing the latest 100; handle these to reveal earlier changes." }
            }
        }
        C.ScrollView {
            visible: root.page === "edit"; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; contentWidth: availableWidth
            ColumnLayout {
                width: parent.width; spacing: Style.space(8)
                Copy { text: "What changed? *" }
                Field { id: titleField; maximumLength: 160; placeholderText: "Installed EasyEffects" }
                RowLayout {
                    Field { id: dateField; maximumLength: 10; placeholderText: "YYYY-MM-DD" }
                    Choice { id: kindField; model: ["Software", "Plugin", "Setting", "Other"] }
                    Choice { id: statusField; model: ["In use", "Trying it", "Needs checking", "Removed / reverted"] }
                }
                Copy { text: "Why? *" }
                Area { id: whyField; placeholderText: "The reason this was useful—not just what it does."; Layout.preferredHeight: Style.space(85) }
                Copy { text: "What changed (optional)" }
                Area { id: detailField; Layout.preferredHeight: Style.space(80) }
                Copy { text: "Backup location (optional; not opened or checked)" }
                Field { id: backupField }
                Copy { text: "How to undo it (optional; saved as text, never run)" }
                Area { id: undoField; Layout.preferredHeight: Style.space(80) }
                Copy { text: "Evidence / source (optional)" }
                Area { id: evidenceField; Layout.preferredHeight: Style.space(70) }
                Copy { text: "Private local notes. Do not put passwords or tokens here. Unsaved drafts survive closing this panel, but not a shell restart."; font.pixelSize: Style.font.caption }
            }
        }
        RowLayout {
            visible: root.page === "edit"
            Action { text: "Save record"; onClicked: root.saveRecord() }
            Action { text: "Discard draft"; onClicked: discardDialog.open() }
        }
        C.Dialog {
            id: discardDialog
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            title: "Discard this unsaved draft?"
            modal: true
            standardButtons: C.Dialog.Yes | C.Dialog.No
            onAccepted: { root.page = "saved"; root.dirty = false; root.eventId = "" }
        }

    }
}
