import Foundation
import FoundationModels

struct Input: Decodable {
    let system: String
    let prompt: String
}

@Generable
struct GroundedResponse {
    @Guide(description: "한국어 답변만 1~3문장. 직접 관련된 자료가 없다면 빈 문자열.")
    var answer: String

    @Guide(description: "답변에 직접 사용한 자료의 번호 목록. 직접 관련된 자료가 없다면 빈 목록.")
    var sourceIDs: [Int]
}

guard SystemLanguageModel.default.isAvailable else {
    exit(2)
}

do {
    let input = try JSONDecoder().decode(Input.self, from: FileHandle.standardInput.readDataToEndOfFile())
    let session = LanguageModelSession(instructions: input.system)
    let result = try await session.respond(
        to: input.prompt, generating: GroundedResponse.self,
        options: GenerationOptions(temperature: 0)
    )
    let output: [String: Any] = ["answer": result.content.answer, "source_ids": result.content.sourceIDs]
    FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: output))
} catch {
    FileHandle.standardError.write(Data("\(type(of: error))\n".utf8))
    exit(1)
}
