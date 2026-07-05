' Generic Blender extension packer.
' Put this file in a Blender extension/add-on directory and double-click it.
' It creates a clean zip package from the current directory, excluding caches,
' old packages, VCS folders, temporary files, and this script itself.

Option Explicit
Randomize

Dim fso, shell, scriptPath, rootPath, rootFolder
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("Shell.Application")

scriptPath = WScript.ScriptFullName
rootPath = fso.GetParentFolderName(scriptPath)
Set rootFolder = fso.GetFolder(rootPath)

RequireRootFile "blender_manifest.toml"
RequireRootFile "__init__.py"

Dim packageId, packageVersion, zipName, zipPath
packageId = ReadManifestValue(fso.BuildPath(rootPath, "blender_manifest.toml"), "id")
packageVersion = ReadManifestValue(fso.BuildPath(rootPath, "blender_manifest.toml"), "version")

If packageId = "" Then
    packageId = SanitizeName(rootFolder.Name)
End If

If packageVersion <> "" Then
    zipName = packageId & "-" & packageVersion & ".zip"
Else
    zipName = packageId & "-" & TimestampName() & ".zip"
End If

zipPath = fso.BuildPath(rootPath, zipName)

Dim tempRoot, tempSource
tempRoot = fso.BuildPath(CreateObject("WScript.Shell").ExpandEnvironmentStrings("%TEMP%"), _
    "blender_extension_pack_" & TimestampName() & "_" & CStr(Int(Rnd() * 100000)))
tempSource = fso.BuildPath(tempRoot, "source")

On Error Resume Next
If fso.FolderExists(tempRoot) Then fso.DeleteFolder tempRoot, True
If fso.FileExists(zipPath) Then fso.DeleteFile zipPath, True
On Error GoTo 0

fso.CreateFolder tempRoot
fso.CreateFolder tempSource

CopyCleanFolder rootPath, tempSource

If CountFilesRecursive(tempSource) = 0 Then
    CleanupAndFail tempRoot, "No files were found to package."
End If

CreateEmptyZip zipPath
ZipFolderContents tempSource, zipPath
ValidateZipRoot zipPath

On Error Resume Next
fso.DeleteFolder tempRoot, True
On Error GoTo 0

If fso.FileExists(zipPath) Then
    MsgBox "Package created:" & vbCrLf & zipPath, vbInformation, "Blender Extension Packer"
Else
    MsgBox "Package failed: zip file was not created.", vbCritical, "Blender Extension Packer"
End If


Sub RequireRootFile(fileName)
    If Not fso.FileExists(fso.BuildPath(rootPath, fileName)) Then
        Fail "Required extension file is missing from the root folder:" & vbCrLf & fileName
    End If
End Sub


Function ReadManifestValue(manifestPath, key)
    ReadManifestValue = ""
    If Not fso.FileExists(manifestPath) Then Exit Function

    Dim file, line, prefix, value
    prefix = key & " = "

    Set file = fso.OpenTextFile(manifestPath, 1, False)
    Do Until file.AtEndOfStream
        line = Trim(file.ReadLine)
        If LCase(Left(line, Len(prefix))) = LCase(prefix) Then
            value = Trim(Mid(line, Len(prefix) + 1))
            If Left(value, 1) = """" Then
                value = Mid(value, 2)
                If InStr(value, """") > 0 Then value = Left(value, InStr(value, """") - 1)
            End If
            ReadManifestValue = SanitizeName(value)
            Exit Do
        End If
    Loop
    file.Close
End Function


Function SanitizeName(value)
    Dim result, invalidChars, i, ch
    result = Trim(CStr(value))
    invalidChars = Array("\", "/", ":", "*", "?", """", "<", ">", "|")
    For i = 0 To UBound(invalidChars)
        result = Replace(result, invalidChars(i), "_")
    Next
    If result = "" Then result = "extension"
    SanitizeName = result
End Function


Function TimestampName()
    Dim d
    d = Now
    TimestampName = _
        CStr(Year(d)) & Pad2(Month(d)) & Pad2(Day(d)) & "-" & _
        Pad2(Hour(d)) & Pad2(Minute(d)) & Pad2(Second(d))
End Function


Function Pad2(value)
    Pad2 = Right("0" & CStr(value), 2)
End Function


Sub CopyCleanFolder(sourcePath, targetPath)
    Dim sourceFolder, subFolder, file, targetSubFolder, targetFile
    Set sourceFolder = fso.GetFolder(sourcePath)

    For Each file In sourceFolder.Files
        If Not ShouldSkipFile(file) Then
            targetFile = fso.BuildPath(targetPath, file.Name)
            fso.CopyFile file.Path, targetFile, True
        End If
    Next

    For Each subFolder In sourceFolder.SubFolders
        If Not ShouldSkipFolder(subFolder) Then
            targetSubFolder = fso.BuildPath(targetPath, subFolder.Name)
            fso.CreateFolder targetSubFolder
            CopyCleanFolder subFolder.Path, targetSubFolder
        End If
    Next
End Sub


Function ShouldSkipFolder(folder)
    Dim name
    name = LCase(folder.Name)

    ShouldSkipFolder = _
        Left(name, 1) = "." Or _
        name = ".git" Or _
        name = ".hg" Or _
        name = ".svn" Or _
        name = "__pycache__" Or _
        name = ".mypy_cache" Or _
        name = ".pytest_cache" Or _
        name = ".ruff_cache" Or _
        name = ".idea" Or _
        name = ".vscode" Or _
        name = "dist" Or _
        name = "build"
End Function


Function ShouldSkipFile(file)
    Dim name, ext
    name = LCase(file.Name)
    ext = LCase(fso.GetExtensionName(file.Name))

    ShouldSkipFile = _
        LCase(file.Path) = LCase(scriptPath) Or _
        Left(name, 1) = "." Or _
        name = ".ds_store" Or _
        name = "thumbs.db" Or _
        ext = "zip" Or _
        ext = "bat" Or _
        ext = "cmd" Or _
        ext = "ps1" Or _
        ext = "vbs" Or _
        ext = "md" Or _
        ext = "pyc" Or _
        ext = "pyo" Or _
        ext = "log" Or _
        ext = "tmp" Or _
        ext = "bak" Or _
        ext = "blend1" Or _
        ext = "blend2"
End Function


Function CountFilesRecursive(folderPath)
    Dim folder, subFolder, total
    Set folder = fso.GetFolder(folderPath)
    total = folder.Files.Count
    For Each subFolder In folder.SubFolders
        total = total + CountFilesRecursive(subFolder.Path)
    Next
    CountFilesRecursive = total
End Function


Sub CreateEmptyZip(path)
    Dim file
    Set file = fso.CreateTextFile(path, True, False)
    file.Write "PK" & Chr(5) & Chr(6) & String(18, Chr(0))
    file.Close
End Sub


Sub ZipFolderContents(sourcePath, destinationZip)
    Dim sourceNs, zipNs, startTime
    Set sourceNs = shell.NameSpace(sourcePath)
    Set zipNs = shell.NameSpace(destinationZip)

    If sourceNs Is Nothing Then
        CleanupAndFail tempRoot, "Could not read temporary package folder."
    End If
    If zipNs Is Nothing Then
        CleanupAndFail tempRoot, "Could not initialize zip file."
    End If

    zipNs.CopyHere sourceNs.Items, 4 + 16 + 1024

    startTime = Timer
    Do While zipNs.Items.Count < sourceNs.Items.Count
        WScript.Sleep 300
        If Timer - startTime > 120 Then Exit Do
    Loop

    WScript.Sleep 700
End Sub


Sub ValidateZipRoot(zipFilePath)
    If Not ZipRootHasFile(zipFilePath, "blender_manifest.toml") Or _
            Not ZipRootHasFile(zipFilePath, "__init__.py") Then
        CleanupAndFail tempRoot, _
            "Package verification failed: required extension files were not found at the zip root." & _
            vbCrLf & "Expected blender_manifest.toml and __init__.py at the top level."
    End If
End Sub


Function ZipRootHasFile(zipFilePath, fileName)
    Dim zipNs, item
    ZipRootHasFile = False
    Set zipNs = shell.NameSpace(zipFilePath)

    If zipNs Is Nothing Then Exit Function

    For Each item In zipNs.Items
        If LCase(item.Name) = LCase(fileName) Then
            ZipRootHasFile = True
            Exit Function
        End If
    Next
End Function


Sub CleanupAndFail(tempPath, message)
    On Error Resume Next
    If fso.FolderExists(tempPath) Then fso.DeleteFolder tempPath, True
    If zipPath <> "" Then
        If fso.FileExists(zipPath) Then fso.DeleteFile zipPath, True
    End If
    On Error GoTo 0
    Fail message
End Sub


Sub Fail(message)
    MsgBox message, vbCritical, "Blender Extension Packer"
    WScript.Quit 1
End Sub
